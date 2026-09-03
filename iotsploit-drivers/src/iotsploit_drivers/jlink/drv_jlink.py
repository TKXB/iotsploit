from __future__ import annotations

import glob
import logging
import os
from typing import Any, Dict, List, Optional

import pylink

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import Device, DeviceType

logger = logging.getLogger(__name__)


def _resolve_jlink_lib_path() -> Optional[str]:
    """Resolve libjlinkarm path from env/default locations."""
    env_path = os.getenv("JLINKARM_LIB")
    if env_path and os.path.exists(env_path):
        return env_path

    # Typical SEGGER install locations on Linux.
    candidates = [
        "/opt/SEGGER/JLink/libjlinkarm.so",
        "/opt/SEGGER/JLink_V918/libjlinkarm.so",
    ]
    candidates.extend(sorted(glob.glob("/opt/SEGGER/JLink_V*/libjlinkarm.so"), reverse=True))
    candidates.extend(sorted(glob.glob("/opt/SEGGER/JLink_V*/arm/libjlinkarm.so"), reverse=True))

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _load_jlink_library() -> tuple[Optional[pylink.library.Library], Optional[str]]:
    """Load pylink library from explicit path first, then fallback to auto-discovery."""
    path = _resolve_jlink_lib_path()
    try:
        if path:
            lib = pylink.library.Library(path)
            if lib.dll() is not None:
                return lib, path
        lib = pylink.Library()
        if lib.dll() is not None:
            return lib, None
    except Exception:
        pass
    return None, path


class JLinkAbility(BaseDeviceDriver):
    REQUIRES = ("module:pylink",)
    """Device driver for SEGGER J-Link debug probes."""

    def __init__(self):
        super().__init__()
        self._jlink_lib, self._jlink_lib_path = _load_jlink_library()
        self._sdk_available = self._jlink_lib is not None
        self.jlink: Optional[pylink.JLink] = None
        self.connected_emulators: list = []

        if not self._sdk_available:
            logger.warning(
                "SEGGER J-Link SDK (libjlinkarm) not found. "
                "Please install J-Link Software from https://www.segger.com/downloads/jlink/ "
                "and ensure libjlinkarm.so is accessible. "
                "You may set JLINKARM_LIB=/path/to/libjlinkarm.so"
            )
        elif self._jlink_lib_path:
            logger.info("Using J-Link library: %s", self._jlink_lib_path)

        self.supported_commands = {
            "read_memory": "Read 32-bit memory at address",
            "write_memory": "Write 32-bit memory at address",
            "reset": "Reset the target MCU",
        }

    # ------------------------------------------------------------------
    # BaseDeviceDriver implementation
    # ------------------------------------------------------------------

    def _scan_impl(self) -> List[Device]:
        if not self._sdk_available:
            logger.warning(
                "J-Link scan skipped: SEGGER J-Link SDK (libjlinkarm) is not installed. "
                "Install from https://www.segger.com/downloads/jlink/"
            )
            return []

        try:
            jlink = pylink.JLink(lib=self._jlink_lib)
            self.connected_emulators = jlink.connected_emulators()
        except Exception as exc:
            logger.error("Error enumerating J-Link emulators: %s", exc)
            return []

        if not self.connected_emulators:
            logger.info("No J-Link emulators found")
            return []

        devices: List[Device] = []
        for emu in self.connected_emulators:
            sn = str(emu.SerialNumber)
            device = Device(
                device_id=f"jlink_{sn}",
                name=f"J-Link ({sn})",
                device_type=DeviceType.JTAG,
                attributes={
                    "emulator_sn": sn,
                    "target_device": "STM32F407VG",
                },
            )
            devices.append(device)
            logger.info("Found J-Link emulator: SN=%s", sn)

        return devices

    def _initialize_impl(self, device: Device) -> bool:
        if not self._sdk_available:
            raise RuntimeError(
                "Cannot initialize: SEGGER J-Link SDK (libjlinkarm) is not installed. "
                "Install from https://www.segger.com/downloads/jlink/"
            )

        emulator_sn = device.attributes.get("emulator_sn")
        if not emulator_sn:
            raise ValueError("Device is missing 'emulator_sn' attribute")

        self.jlink = pylink.JLink(lib=self._jlink_lib)
        self.jlink.open(serial_no=int(emulator_sn))

        target_device = device.attributes.get("target_device", "STM32F407VG")
        self.jlink.connect(target_device)
        logger.info("J-Link initialized: %s -> %s", device.name, target_device)
        return True

    def _connect_impl(self, device: Device) -> bool:
        if self.jlink is None:
            raise RuntimeError("J-Link not initialised – call initialize first")
        # Already connected during initialize; just verify
        return self.jlink.connected()

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Any:
        if self.jlink is None:
            raise RuntimeError("J-Link device not initialised")

        if args is None:
            args = {}

        if command == "read_memory":
            address = int(args.get("address", 0x08000000))
            count = int(args.get("count", 10))
            mem = self.jlink.memory_read32(address, count)
            return {"address": hex(address), "count": count, "data": mem}

        if command == "write_memory":
            address = int(args.get("address", 0x20000000))
            data = args.get("data", [0x12345678])
            self.jlink.memory_write32(address, data)
            return {"address": hex(address), "written": len(data)}

        if command == "reset":
            self.jlink.reset()
            return {"status": "success", "message": f"Reset {device.name}"}

        raise ValueError(f"Unsupported command: {command}")

    def _reset_impl(self, device: Device) -> bool:
        if self.jlink:
            self.jlink.reset()
            logger.info("Reset J-Link device: %s", device.name)
            return True
        return False

    def _close_impl(self, device: Device) -> bool:
        if self.jlink:
            self.jlink.close()
            self.jlink = None
            logger.info("Closed J-Link device: %s", device.name)
        return True

    def _recovery_impl(self, device: Device, recovery_type: str, **kwargs) -> dict:
        raise NotImplementedError("Recovery operations not implemented for J-Link driver")

    def _get_supported_recovery_operations_impl(self) -> list:
        return []
