from __future__ import annotations

import glob
import logging
import os
from typing import Any, Dict, List, Optional

import pylink

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_core.domain.monitoring import usb_resource

logger = logging.getLogger(__name__)

# Canonical register names (see iotsploit_core.ports.debug_access) as the J-Link
# DLL lists them for a Cortex-M; it rejects any name it does not list.
_REGISTER_NAMES = {
    **{f"r{index}": f"R{index}" for index in range(13)},
    "sp": "R13 (SP)", "lr": "R14", "pc": "R15 (PC)",
    "xpsr": "XPSR", "msp": "MSP", "psp": "PSP", "control": "CONTROL",
}
SEGGER_USB_VENDOR_ID = 0x1366


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
    """Device driver for SEGGER J-Link debug probes.

    Also a ``DebugAccess`` backend: target monitors use it as a plain transport
    and do all decoding in ``iotsploit_core.core.monitoring.arch``.
    """

    REQUIRES = ("module:pylink",)
    DEBUG_USB_VENDOR_IDS = (SEGGER_USB_VENDOR_ID,)

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
            "read_memory": {
                "description": "Read 32-bit memory at address",
                "parameters": {
                    "address": {"type": "str", "required": True,
                                "description": "Start address, e.g. 0x08000000"},
                    "count": {"type": "int", "required": False, "default": 10,
                              "description": "Number of 32-bit words to read"},
                },
            },
            "write_memory": {
                "description": "Write 32-bit memory at address",
                "parameters": {
                    "address": {"type": "str", "required": True,
                                "description": "Target address, e.g. 0x20000000"},
                    "data": {"type": "list", "required": True,
                             "description": "32-bit words to write"},
                },
            },
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
            product = getattr(emu, "acProduct", b"")
            if isinstance(product, bytes):
                product = product.decode(errors="replace").rstrip("\x00")
            product = str(product).strip()
            # The product names the probe's own MCU (an nRF52840-DK's on-board
            # J-Link runs on an nRF5340), never the attached target.
            device = Device(
                device_id=f"jlink_{sn}",
                name=f"{product or 'J-Link'} ({sn})",
                device_type=DeviceType.USB,
                attributes={"emulator_sn": sn, "product": product},
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
        target_device = device.attributes.get("target_device")
        if not target_device:
            raise ValueError("J-Link needs an explicit target_device; a probe cannot identify its target")

        secured = []

        def refuse_unsecure(title, msg, flags):
            # Unsecuring mass-erases the target; record the request and decline.
            secured.append(msg)
            return pylink.enums.JLinkFlags.DLG_BUTTON_NO

        self.jlink = pylink.JLink(lib=self._jlink_lib, unsecure_hook=refuse_unsecure)
        try:
            self.jlink.open(serial_no=int(emulator_sn))
        except Exception as exc:
            raise RuntimeError(f"Cannot open J-Link {emulator_sn}: {exc}") from exc

        try:
            if device.attributes.get("interface") == "swd":
                self.jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
            self.jlink.connect(target_device)
        except Exception as exc:
            self.jlink.close()
            self.jlink = None
            if secured:
                raise RuntimeError(
                    f"{target_device} is readback-protected (APPROTECT); debug access "
                    "requires an unlock, which mass-erases its flash"
                ) from exc
            raise RuntimeError(
                f"Cannot connect J-Link {emulator_sn} to {target_device}: {exc}"
            ) from exc
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
            self.jlink.reset(halt=False)
            return {"status": "success", "message": f"Reset {device.name}"}

        raise ValueError(f"Unsupported command: {command}")

    def resource_key(self, device: Device) -> Optional[str]:
        serial = device.attributes.get("emulator_sn")
        return usb_resource(SEGGER_USB_VENDOR_ID, serial, "debug") if serial else None

    # ------------------------------------------------------------------
    # DebugAccess (iotsploit_core.ports.debug_access)
    # ------------------------------------------------------------------

    def debug_architectures(self) -> frozenset[str]:
        return frozenset({"cortex_m"})

    def attach(self, serial: str, target: str | None, *, interface: str = "swd") -> None:
        # No target: initialize refuses before opening, as a J-Link must be told its device.
        device = Device(
            device_id=f"jlink_{serial}",
            name=f"J-Link {serial}",
            device_type=DeviceType.USB,
            attributes={"emulator_sn": str(serial), "target_device": target, "interface": interface},
        )
        self.initialize(device)
        self.device = device

    def detach(self) -> None:
        if self.jlink is not None:
            self.jlink.close()
            self.jlink = None

    def read_mem32(self, address: int, count: int = 1) -> list[int]:
        return list(self._attached().memory_read32(address, count))

    def read_registers(self, names) -> list[int]:
        try:
            dll_names = [_REGISTER_NAMES[name] for name in names]
        except KeyError as exc:
            raise ValueError(f"Unknown core register {exc.args[0]!r}") from None
        return list(self._attached().register_read_multiple(dll_names))

    def halt(self) -> None:
        self._attached().halt()

    def is_halted(self) -> bool:
        return bool(self._attached().halted())

    def resume(self) -> None:
        self._attached().restart()

    def reset_core(self, *, halt: bool = False) -> None:
        self._attached().reset(halt=halt)

    def _attached(self) -> pylink.JLink:
        if self.jlink is None:
            raise RuntimeError("J-Link is not initialized")
        return self.jlink

    def _reset_impl(self, device: Device) -> bool:
        if self.jlink:
            self.jlink.reset(halt=False)
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
