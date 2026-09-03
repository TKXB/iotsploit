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
   applies one CAN FD configuration on initialize -- the same
   ``ip link set ... type can ... fd on`` an operator would type -- and lowers
   the link again on close, which the inherited close already does for a link
   its driver raised.
"""

from typing import Dict, List

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
    """A PEAK PCAN adapter, configured for CAN FD and lowered again on close."""

    DEVICE_ID_PREFIX = 'pcan_'

    @staticmethod
    def _is_peak(info: CanLinkInfo) -> bool:
        return bool(info.timing_const) and info.timing_const.startswith(PEAK_TIMING_PREFIXES)

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
        """Apply the CAN FD configuration and raise the link.

        Unconditional, unlike the SocketCAN driver's initialize, which leaves an
        already-up link alone: an adapter that is up on the wrong bit timing is
        the failure this exists to prevent, and only a reconfiguration fixes it.
        Bit timing cannot be set on a running link, so ``can-fd-up`` lowers the
        link, configures it, and raises it -- one privileged call, so the link
        is never left down by a half-finished sequence.
        """
        if not isinstance(device, SocketCANDevice):
            raise ValueError("This plugin only supports SocketCAN devices")

        info = read_can_links().get(device.interface)
        if info is None:
            raise RuntimeError(f"{device.interface} is not a CAN interface on this host")
        if not self._is_peak(info):
            raise RuntimeError(
                f"{device.interface} is not a PEAK adapter "
                f"(its controller reports {info.timing_const or 'no bit timing'})"
            )

        self._run_privileged("can-fd-up", {"iface": device.interface, **FD_TIMING})
        # This driver raised the link, so the inherited close and reset may
        # lower and cycle it.
        self._brought_link_up = True
        self.current_interface = device.interface
        self.device = device

        # Read back rather than echo: the configuration that matters is the one
        # the kernel accepted, and it is what the operator will see in ip link.
        configured = read_can_links().get(device.interface) or info
        device.attributes.update(self._device_for(configured).attributes)
        logger.info("PCAN device initialized on %s: %s", device.interface, configured.describe())
        return True

    def status(self) -> Dict:
        state = super().status()
        # Only when this driver raised the link is the timing below the timing
        # that is actually on it.
        state["fd_timing"] = dict(FD_TIMING) if self._brought_link_up else None
        return state
