"""PEAK PCAN device driver.

A PEAK adapter reaches the host as an ordinary SocketCAN interface, so
everything about *reading* one -- error-frame classification, streaming,
sending -- is the SocketCAN driver's job and is inherited here unchanged. Two
things differ, and they are the whole reason this driver exists:

1. **It knows which interface is the adapter.** The scan matches on the
   bit-timing constants the kernel prints for the controller behind the
   interface, so a rig carrying a PCAN-USB FD and a vcan reports the adapter
   here and not the loopback.

2. **It owns the link.** :class:`SocketCANDriver` will not configure a bus,
   because it cannot know what the bus is. A PEAK adapter is brought to a
   vehicle for a test and is configured by whoever plugs it in, so this driver
   exposes ``can-up`` and ``can-down`` commands that apply the same
   ``ip link set ... type can ... fd on`` an operator would type. Initialize
   validates the adapter but leaves the link untouched; the operator decides
   when to bring it up and take it down.
"""

from typing import Dict, List, Optional

from iotsploit_core.domain.device import Device, SocketCANDevice
from iotsploit_core.utils import iots_logger

from iotsploit_drivers.socketcan.can_link import CanLinkInfo, read_can_links
from iotsploit_drivers.socketcan.drv_socketcan import SocketCANDriver

logger = iots_logger.get_logger(__name__)

#: Every PEAK controller the kernel supports names its bit-timing constants
#: after itself: ``pcan_usb``, ``pcan_usb_fd``, ``pcan_usb_pro_fd`` for the USB
#: adapters, ``peak_pci``, ``peak_pciefd``, ``peak_canfd`` for the cards. The
#: two prefixes cover the family without pinning a model that ships next year.
PEAK_TIMING_PREFIXES = ("pcan", "peak")

#: The CAN FD configuration this driver applies when it brings a PEAK link up:
#: 500 kbit/s arbitration and 2 Mbit/s data, both sampled at 75% of the bit.
#: Every value is stated because a bit timing is not a default -- an interface
#: brought up on the wrong one reads nothing but error frames, and the driver
#: that chose it should be the one an operator can read it off.
FD_TIMING = {
    "bitrate": 500_000,
    "sample_point": 0.750,
    "dbitrate": 2_000_000,
    "dsample_point": 0.750,
}


class PCANDriver(SocketCANDriver):
    """A PEAK PCAN adapter, with manual ``can-up``/``can-down`` link control."""

    DEVICE_ID_PREFIX = 'pcan_'

    def __init__(self):
        super().__init__()
        self.supported_commands.update({
            "can-up": "Bring the PEAK link up with CAN FD configuration",
            "can-down": "Lower the PEAK link",
        })

    @staticmethod
    def _is_peak(info: CanLinkInfo) -> bool:
        return bool(info.timing_const) and info.timing_const.startswith(PEAK_TIMING_PREFIXES)

    def _peak_link(self, iface: str) -> CanLinkInfo:
        """The kernel's view of a PEAK interface, or an error naming what it is instead."""
        info = read_can_links().get(iface)
        if info is None:
            raise RuntimeError(f"{iface} is not a CAN interface on this host")
        if not self._is_peak(info):
            raise RuntimeError(
                f"{iface} is not a PEAK adapter "
                f"(its controller reports {info.timing_const or 'no bit timing'})"
            )
        return info

    def _scan_impl(self) -> List[Device]:
        """Only the PEAK adapters, reported exactly as the kernel has them now.

        A PEAK link that is down is still listed: it is what this driver is for
        -- an unconfigured adapter is the normal state before initialize.
        """
        logger.info("Starting scan for PEAK CAN adapters...")
        devices = []

        for info in sorted(read_can_links().values(), key=lambda link: link.name):
            if not self._is_peak(info):
                continue
            logger.info("Found PEAK CAN adapter: %s", info.describe())
            devices.append(self._device_for(info))

        logger.info("Scan complete. Found %d PEAK CAN adapters", len(devices))
        return devices

    def _device_for(self, info: CanLinkInfo) -> SocketCANDevice:
        device = super()._device_for(info)
        device.name = f"PCAN_{info.name}"
        device.attributes['description'] = f"PEAK CAN adapter ({info.timing_const})"
        return device

    def _initialize_impl(self, device: SocketCANDevice) -> bool:
        """Validate the adapter and record it, but leave the link untouched.

        The link is brought up and configured by the ``can-up`` command, not
        here: an operator who wants to inspect the adapter before committing
        to a bit timing can do so, and a link that is already up on the wrong
        timing is left alone until the operator decides to reconfigure it.
        """
        if not isinstance(device, SocketCANDevice):
            raise ValueError("This plugin only supports SocketCAN devices")

        info = self._peak_link(device.interface)

        self.current_interface = device.interface
        self.device = device
        device.attributes.update(self._device_for(info).attributes)
        logger.info("PCAN device initialized on %s: %s", device.interface, info.describe())
        return True

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Optional[str]:
        """Handle ``can-up``/``can-down`` before delegating streaming to the parent."""
        command = command.lower()
        if command not in ("can-up", "can-down"):
            return super()._command_impl(device, command, args)

        # The interface comes from the device this command was addressed to, not
        # from self.current_interface: the manager resolves the device straight
        # out of the scan and never requires an initialize, so on the command
        # path that attribute is usually unset -- and on a rig with two PEAK
        # adapters it names whichever was initialized, not the one addressed.
        iface = getattr(device, "interface", None) or self.current_interface
        if not iface:
            raise RuntimeError("This command needs a scanned PEAK device to act on")
        self._peak_link(iface)
        # Whatever the operator addressed is what connect and streaming will use.
        self.current_interface = iface
        self.device = device

        if command == "can-up":
            self._run_privileged("can-fd-up", {"iface": iface, **FD_TIMING})
            self._brought_link_up = True
        else:
            self._run_privileged("can-link-state", {"iface": iface, "state": "down"})
            self._brought_link_up = False

        # Report the link as the kernel now has it, not as it was asked to be.
        configured = self._peak_link(iface)
        device.attributes.update(self._device_for(configured).attributes)
        logger.info("PCAN %s on %s: %s", command, iface, configured.describe())
        if command == "can-up":
            return f"can-up: {iface} configured with FD timing"
        return f"can-down: {iface} lowered"

    def status(self) -> Dict:
        state = super().status()
        # Only when this driver raised the link is the timing below the timing
        # that is actually on it.
        state["fd_timing"] = dict(FD_TIMING) if self._brought_link_up else None
        return state
