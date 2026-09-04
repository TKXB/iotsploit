"""SocketCAN device driver.

Two rules this driver learned the hard way, both from a bench Pi on a live
CAN FD bus:

1. **An error frame is not a message.** A SocketCAN socket delivers bus faults
   alongside traffic, and python-can enables them by default. python-can masks
   ``CAN_ERR_FLAG`` off before exposing ``arbitration_id``, so a controller
   fault reads as a frame with id ``0x004`` -- an ECU that does not exist.
   Every received frame is classified before anything looks at its identity.
   See ``can_errors``.

2. **The link belongs to the operator.** Bitrate, data bitrate, FD mode, and
   link state are host configuration. This driver reads them; it does not
   invent them, and it does not take down a link it did not bring up.
   See ``can_link``.
"""

import time
from typing import Dict, List, Optional

import can

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.core.stream_manager import StreamAction, StreamData, StreamSource, StreamType
from iotsploit_core.domain.device import Device, SocketCANDevice
from iotsploit_core.utils import iots_logger
from iotsploit_priv import PrivilegedHelperError, call as privileged_call

from iotsploit_drivers.socketcan.can_errors import decode_error_frame
from iotsploit_drivers.socketcan.can_link import CanLinkInfo, read_can_links

logger = iots_logger.get_logger(__name__)

#: A faulted bus repeats the same error hundreds of times a second. Each
#: distinct fault is reported at most this often, so the log and the stream
#: stay readable while the fault is still visible.
#:
#: Per description rather than globally, because the interesting case
#: oscillates: a controller sitting on the error-passive threshold alternates
#: rx-error-warning and rx-error-passive on every frame, so "report whenever
#: the description changes" would report every single one -- 59 of them in
#: three seconds on a real bench bus, which is the flood this exists to stop.
ERROR_REPORT_INTERVAL_S = 1.0


class SocketCANDriver(BaseDeviceDriver):
    REQUIRES = ("platform:linux", "module:can")

    #: Device ids are namespaced per driver: DeviceStore keys by device_id
    #: alone, so two drivers that both find can0 must not name it the same.
    DEVICE_ID_PREFIX = 'can_'

    def __init__(self):
        super().__init__()
        self.bus = None
        self.current_interface = None
        # Whether *this* driver brought the link up. Only then may it take it
        # back down: an interface the operator configured outlives us.
        self._brought_link_up = False
        self._error_counts: Dict[str, int] = {}
        self._last_error_report: Dict[str, float] = {}
        self.supported_commands = {
            "start": "Start streaming CAN messages",
            "stop": "Stop streaming CAN messages",
            "dump": "Display current CAN interface status",
            "send": "Send a CAN message"
        }

    def _scan_impl(self) -> List[Device]:
        """扫描可用的CAN接口

        Attributes come from the kernel. An interface whose bitrate is unknown
        reports ``None`` rather than a plausible-looking default: a wrong
        bitrate that looks configured is worse than an absent one.
        """
        logger.info("Starting scan for SocketCAN interfaces...")
        devices = []

        for info in sorted(read_can_links().values(), key=lambda link: link.name):
            logger.info("Found CAN interface: %s", info.describe())
            devices.append(self._device_for(info))

        logger.info("Scan complete. Found %d SocketCAN interfaces", len(devices))
        return devices

    def _device_for(self, info: CanLinkInfo) -> SocketCANDevice:
        """One scanned interface as a device, carrying only what the kernel said."""
        return SocketCANDevice(
            device_id=self._device_id_for(info.name),
            name=f"SocketCAN_{info.name}",
            interface=info.name,
            attributes={
                'description': 'Virtual SocketCAN Interface' if info.is_virtual else 'SocketCAN Interface',
                'type': 'CAN',
                'bitrate': info.bitrate,
                'dbitrate': info.dbitrate,
                'supports_fd': info.supports_fd,
                'is_up': info.is_up,
                'controller_state': info.controller_state,
                'timing_const': info.timing_const,
                'is_virtual': info.is_virtual,
            },
        )

    @classmethod
    def _device_id_for(cls, interface: str) -> str:
        """Stable id for an interface name, unchanged from the original scheme."""
        digits = ''.join(filter(str.isdigit, interface))
        interface_num = (int(digits) if digits else 0) + 1
        prefix = 'vcan_' if interface.startswith('vcan') else cls.DEVICE_ID_PREFIX
        return f"{prefix}{str(interface_num).zfill(3)}"

    def _initialize_impl(self, device: SocketCANDevice) -> bool:
        """初始化CAN接口

        An interface that is already up is left exactly as it is. Bitrate cannot
        be changed on a live link anyway, and an operator who configured a bus
        for CAN FD did not ask for it to be reset to classic 500k.
        """
        if not isinstance(device, SocketCANDevice):
            raise ValueError("This plugin only supports SocketCAN devices")

        info = read_can_links().get(device.interface)
        if info is None:
            raise RuntimeError(f"{device.interface} is not a CAN interface on this host")

        self._brought_link_up = False

        if info.is_up:
            logger.info("Using %s as configured: %s", device.interface, info.describe())
        else:
            self._bring_link_up(device, info)

        self.current_interface = device.interface
        self.device = device
        logger.info("SocketCAN device initialized on %s", device.interface)
        return True

    def _bring_link_up(self, device: SocketCANDevice, info: CanLinkInfo) -> None:
        """Bring a down interface up, using only a bitrate somebody chose.

        The caller's attribute wins over what the kernel remembers; neither is
        invented here. A real interface with no bitrate anywhere cannot be
        brought up at all, and saying so beats guessing 500k and producing a
        bus that reads nothing but errors.
        """
        bitrate = device.attributes.get('bitrate') or info.bitrate

        if not info.is_virtual and not bitrate:
            raise RuntimeError(
                f"{device.interface} is down and has no bitrate configured. "
                "Choose the physical CAN bitrate before initializing it."
            )

        self._run_privileged(
            "can-up",
            {"iface": device.interface, "bitrate": None if info.is_virtual else int(bitrate)},
        )
        self._brought_link_up = True
        logger.info("Brought %s up at %s bit/s", device.interface, bitrate or "virtual")

    @staticmethod
    def _run_privileged(verb: str, args: dict) -> None:
        try:
            result = privileged_call(verb, args)
        except PrivilegedHelperError as exc:
            raise RuntimeError(str(exc)) from exc
        if not result.ok:
            raise RuntimeError(result.stderr or f"{verb} failed with exit {result.exit}")

    def _connect_impl(self, device: SocketCANDevice) -> bool:
        """连接到CAN接口"""
        if not self.current_interface:
            logger.error("Device not initialized. Please initialize first.")
            raise RuntimeError("Device not initialized")

        try:
            self.setup_bus()
            logger.info(f"Connected to SocketCAN device on {device.interface}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SocketCAN device: {e}")
            raise

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Optional[str]:
        """执行设备命令"""
        logger.debug(f"Received command: '{command}', args: {args}")
        try:
            command = command.lower()
            if command == "start":
                self.start_streaming(device)
                logger.info("Started CAN streaming")
                return "Started CAN streaming"

            elif command == "stop":
                self.stop_streaming(device)
                logger.info("Stopped CAN streaming")
                return "Stopped CAN streaming"

            elif command == "dump":
                status = self.status()
                logger.info(f"CAN Interface Status: {status}")
                return str(status)

            elif command == "send":
                if not args:
                    raise ValueError("Missing arguments for send command")
                return self._command_send(device, args)

            else:
                logger.error(f"Unknown command: {command}")
                raise ValueError(f"Unknown command: {command}")

        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            raise

    def _command_send(self, device: Device, args: Dict) -> str:
        """Send one frame, with nothing defaulted.

        The original defaulted to id 0x123 carrying DEADBEEF, so a malformed
        request put an invented frame on a real vehicle bus. An incomplete send
        request is now an error.
        """
        if 'id' not in args or args.get('id') is None:
            raise ValueError("send requires a CAN id")
        if not args.get('data'):
            raise ValueError("send requires data")

        can_id = args['id']
        can_id = int(can_id, 16) if isinstance(can_id, str) else int(can_id)
        data = args['data']
        data = bytes.fromhex(data) if isinstance(data, str) else bytes(data)

        self.send_can_message(
            device,
            can_id,
            data,
            is_extended_id=bool(args.get('is_extended_id', False)),
            is_fd=bool(args.get('is_fd', False)),
        )
        return f"Sent CAN message - ID: {hex(can_id)}, Data: {data.hex()}"

    def status(self) -> Dict:
        """What this driver currently has open, and what the bus is doing."""
        return {
            "is_acquiring": self.is_acquiring.is_set(),
            "interface": self.current_interface,
            "bus_active": self.bus is not None,
            "owns_link": self._brought_link_up,
            "bus_errors": dict(self._error_counts),
        }

    def _reset_impl(self, device: SocketCANDevice) -> bool:
        """重置CAN接口

        Only a link this driver brought up gets cycled. Restarting an interface
        the operator configured would disrupt every other reader on it,
        including their own candump.
        """
        if not self.current_interface:
            return False
        if not self._brought_link_up:
            raise RuntimeError(
                f"{self.current_interface} was configured outside IoTSploit; reset it with its owning system service"
            )

        logger.info(f"Resetting interface {self.current_interface}")
        self._run_privileged("can-link-state", {"iface": self.current_interface, "state": "down"})
        self._run_privileged("can-link-state", {"iface": self.current_interface, "state": "up"})
        logger.info("SocketCAN device reset successfully")
        return True

    def _close_impl(self, device: SocketCANDevice) -> bool:
        """关闭CAN接口"""
        try:
            logger.info(f"Closing SocketCAN device on {self.current_interface}")
            self.stop_streaming(device)
            self.shutdown_bus()
            self.bus = None

            if self._brought_link_up and self.current_interface:
                self._run_privileged("can-link-state", {"iface": self.current_interface, "state": "down"})
                self._brought_link_up = False
            elif self.current_interface:
                logger.info("Leaving %s up: this driver did not bring it up", self.current_interface)

            self.current_interface = None
            logger.info("SocketCAN device closed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to close SocketCAN device: {e}")
            raise

    def _setup_acquisition(self, device: Device):
        """设置CAN数据采集"""
        logger.info("Setting up CAN acquisition")
        self._error_counts.clear()
        self._last_error_report.clear()
        if not self.bus:
            self.setup_bus()

    def _cleanup_acquisition(self, device: Device):
        """清理CAN数据采集"""
        logger.info("Cleaning up CAN acquisition")
        if self.bus:
            self.shutdown_bus()
            self.bus = None

    def _acquisition_loop(self):
        """CAN数据采集循环"""
        logger.info("Starting CAN acquisition loop")
        while self.is_acquiring.is_set():
            try:
                message = self.bus.recv(timeout=0.1)
                if not self.is_acquiring.is_set():
                    break
                if message:
                    self.handle_received_message(message)

                self._pump_client_data()

            except Exception as e:
                logger.error(f"Error in CAN acquisition loop: {str(e)}")
                time.sleep(0.1)
        logger.info("CAN acquisition loop stopped")

    def handle_received_message(self, message) -> None:
        """Classify one received frame, then broadcast it as what it is.

        The order matters: ``is_error_frame`` is checked before anything reads
        ``arbitration_id``, because on an error frame that field is an error
        class and not an address.
        """
        if message.is_error_frame:
            self._report_bus_error(message)
            return

        channel = self.device.device_id if self.device else (self.current_interface or "can")
        stream_data = StreamData(
            stream_type=StreamType.CAN,
            channel=channel,
            timestamp=message.timestamp or time.time(),
            source=StreamSource.SERVER,
            action=StreamAction.DATA,
            data={
                'id': hex(message.arbitration_id),
                'data': message.data.hex(),
                'dlc': message.dlc
            },
            metadata={
                'interface': self.current_interface,
                'is_extended_id': message.is_extended_id,
                'is_fd': bool(getattr(message, 'is_fd', False)),
                'is_remote_frame': bool(getattr(message, 'is_remote_frame', False)),
            }
        )
        self.stream_wrapper.broadcast_data(stream_data)
        # DEBUG, not INFO: a live bus is thousands of frames a second.
        logger.debug(
            "CAN frame - ID: %s, Data: %s, DLC: %s",
            hex(message.arbitration_id), message.data.hex(), message.dlc,
        )

    def _report_bus_error(self, message) -> None:
        """Record a bus fault and report it as bus health, never as traffic."""
        error = decode_error_frame(message.arbitration_id, message.data)
        description = error["description"]
        self._error_counts[description] = self._error_counts.get(description, 0) + 1

        # A fault never seen before has no entry, so it reports immediately.
        now = time.monotonic()
        if now - self._last_error_report.get(description, float("-inf")) < ERROR_REPORT_INTERVAL_S:
            return
        self._last_error_report[description] = now

        logger.warning(
            "CAN bus error on %s: %s (%d so far)",
            self.current_interface, description, self._error_counts[description],
        )

        channel = self.device.device_id if self.device else (self.current_interface or "can")
        self.stream_wrapper.broadcast_data(
            StreamData(
                stream_type=StreamType.CAN,
                channel=channel,
                timestamp=message.timestamp or time.time(),
                source=StreamSource.SERVER,
                # Not DATA: this did not come from an ECU, and a client that
                # renders CAN traffic must not list it as a frame.
                action=StreamAction.ERROR,
                data={'kind': 'bus_error', **error, 'counts': dict(self._error_counts)},
                metadata={'interface': self.current_interface},
            )
        )

    def _pump_client_data(self) -> None:
        """Forward one queued client frame to the bus, if there is one."""
        client_data = self.stream_manager.get_client_data()
        if not client_data or client_data.stream_type != StreamType.CAN:
            return

        try:
            can_data = client_data.data
            can_id = can_data['id']
            can_id = int(can_id, 16) if isinstance(can_id, str) else int(can_id)
            data = can_data['data']
            data = bytes.fromhex(data) if isinstance(data, str) else bytes(data)
            metadata = client_data.metadata or {}

            message = can.Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=bool(metadata.get('is_extended_id', can_data.get('is_extended_id', False))),
                is_fd=bool(metadata.get('is_fd', can_data.get('is_fd', False))),
            )
            self.bus.send(message)
            logger.info(
                "Sent client CAN message - ID: %s, Data: %s",
                hex(message.arbitration_id), message.data.hex(),
            )
        except Exception as e:
            logger.error(f"Failed to process client CAN data: {e}")

    def setup_bus(self):
        """设置CAN总线

        FD reception is enabled unconditionally, which is what ``candump`` does
        too. It must not be conditioned on the interface MTU: a PEAK PCAN-USB
        FD on a bench bus reports ``mtu 16`` -- classic -- while delivering
        nothing but CAN FD frames, so a socket opened from that MTU receives
        the error frames and not one frame of traffic. Enabling it costs
        nothing on a genuinely classic link, where no FD frame ever arrives.

        Sending is unaffected: an FD frame still requires an FD-configured
        link, and ``supports_fd`` on the device says whether that will work.

        ``ignore_config`` keeps a stray ~/.canrc from redirecting the bus.
        """
        supports_fd = bool(self.device.attributes.get('supports_fd')) if self.device else False
        logger.info(
            "Setting up CAN bus on interface %s (link reports %s; receiving both)",
            self.current_interface, "FD" if supports_fd else "classic",
        )
        self.bus = can.interface.Bus(
            channel=self.current_interface,
            interface='socketcan',
            fd=True,
            ignore_config=True,
        )
        logger.debug("CAN bus setup complete")

    def shutdown_bus(self):
        """关闭CAN总线"""
        if self.bus:
            try:
                logger.info("Shutting down CAN bus")
                self.bus.shutdown()
                logger.debug("CAN bus shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")

    def send_can_message(self, device: Device, can_id: int, data: bytes,
                         is_extended_id: bool = False, is_fd: bool = False):
        """发送CAN消息

        The flags are parameters rather than constants: a driver that always
        sent standard classic frames could not address an extended id or an FD
        bus at all.
        """
        if not self.bus:
            logger.error("Cannot send message: SocketCAN device not connected")
            raise RuntimeError("Cannot send message: SocketCAN device not connected")

        try:
            message = can.Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=is_extended_id,
                is_fd=is_fd,
            )
            self.bus.send(message)
            logger.info(
                "Sent CAN message - ID: %s, Data: %s",
                hex(message.arbitration_id), message.data.hex(),
            )
        except Exception as e:
            logger.error(f"Failed to send CAN message: {e}")
            raise
