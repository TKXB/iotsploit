from __future__ import annotations

import glob
import logging
import os
import time
from typing import Any, Dict, List, Optional

import pylink

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import Device, DeviceType

logger = logging.getLogger(__name__)

_TARGETS = {
    "NRF52840_XXAA": {
        "cpuid_part": 0xC24,
        "resetreas": 0x40000400,
        "ram": (0x20000000, 0x20040000),
    },
    "NRF5340_XXAA_APP": {
        "cpuid_part": 0xD21,
        "resetreas": 0x40005400,
        "ram": (0x20000000, 0x20080000),
    },
}

_CFSR_BITS = {
    0: "instruction access violation",
    1: "data access violation",
    3: "exception return unstacking fault",
    4: "exception entry stacking fault",
    5: "lazy floating-point state fault",
    8: "instruction bus error",
    9: "precise data bus error",
    10: "imprecise data bus error",
    11: "bus fault on exception return",
    12: "bus fault on exception entry",
    13: "lazy floating-point bus fault",
    16: "undefined instruction",
    17: "invalid execution state",
    18: "invalid exception return",
    19: "coprocessor access fault",
    20: "stack limit violation",
    24: "unaligned access",
    25: "divide by zero",
}
_HFSR_BITS = {
    1: "vector-table hard fault",
    30: "escalated configurable fault",
    31: "debug event hard fault",
}
_EXCEPTIONS = {3: "HardFault", 4: "MemManage", 5: "BusFault", 6: "UsageFault"}


def _fault_causes(cfsr: int, hfsr: int, exception: int) -> list[str]:
    causes = [name for bit, name in _CFSR_BITS.items() if cfsr & (1 << bit)]
    causes.extend(name for bit, name in _HFSR_BITS.items() if hfsr & (1 << bit))
    if not causes and exception in _EXCEPTIONS:
        causes.append(f"active {_EXCEPTIONS[exception]}")
    return causes


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
            "core_status": "Observe a supported Nordic MCU without halting",
            "fault_snapshot": "Halt after a fault and capture core registers",
            "recover_target": "Reset, run, and wait for a usable core",
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

        if command == "core_status":
            return self.core_status(device)

        if command == "fault_snapshot":
            return self.fault_snapshot(device)

        if command == "recover_target":
            return self.recover_target(
                device,
                reset=bool(args.get("reset", True)),
                timeout_ms=int(args.get("timeout_ms", 5000)),
            )

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

    def core_status(self, device: Device) -> dict:
        """Read-to-clear DHCSR is consumed exactly once per observation."""
        target = device.attributes.get("target_device")
        profile = _TARGETS.get(target)
        if profile is None:
            raise ValueError(f"Core monitoring does not support {target!r}")
        if self.jlink is None:
            raise RuntimeError("J-Link is not initialized")
        started = time.monotonic()
        registers = {}
        observation = {
            "target": target, "probe_serial": device.attributes["emulator_sn"],
            "observed_at": time.time(), "sample_started": started,
            "registers": registers, "state": "unavailable", "crashed": False,
            "stop_reason": None,
        }
        try:
            for name, address in (
                ("cpuid", 0xE000ED00), ("dhcsr", 0xE000EDF0), ("icsr", 0xE000ED04),
                ("cfsr", 0xE000ED28), ("hfsr", 0xE000ED2C),
                ("resetreas", profile["resetreas"]),
            ):
                words = self.jlink.memory_read32(address, 1)
                if len(words) != 1:
                    raise RuntimeError(f"Incomplete {name} read")
                registers[name] = words[0]
            part = (registers["cpuid"] >> 4) & 0xFFF
            if part != profile["cpuid_part"]:
                raise RuntimeError(
                    f"Expected CPUID part 0x{profile['cpuid_part']:03X}, "
                    f"read 0x{registers['cpuid']:08X}; verify target and debug access"
                )
            cfsr = registers["cfsr"]
            for name, address, valid in (
                ("mmfar", 0xE000ED34, cfsr & (1 << 7)),
                ("bfar", 0xE000ED38, cfsr & (1 << 15)),
            ):
                if valid:
                    registers[name] = self.jlink.memory_read32(address, 1)[0]
            dhcsr = registers["dhcsr"]
            exception = registers["icsr"] & 0x1FF
            fault_causes = _fault_causes(cfsr, registers["hfsr"], exception)
            observation.update(retired=bool(dhcsr & (1 << 24)),
                               reset_observed=bool(dhcsr & (1 << 25)),
                               active_exception=exception,
                               fault_causes=fault_causes)
            # An active fault handler outranks a halt: connecting to a locked-up
            # core halts it inside its HardFault. Fault status bits with no
            # active handler describe a fault firmware already handled; they
            # stay in fault_causes as evidence.
            if dhcsr & (1 << 19):
                state, cause, crashed = "lockup", "CPU lockup", True
            elif exception in _EXCEPTIONS:
                details = ", ".join(fault_causes) or "unknown fault"
                state, cause, crashed = "fault", f"Fault evidence observed: {details}", False
            elif dhcsr & (1 << 17):
                state, cause, crashed = "halted", "Unexpected debug halt", False
            elif dhcsr & (1 << 25):
                state, cause, crashed = "reset", "Reset observed; cause and input attribution unconfirmed", False
            else:
                state = "sleeping" if dhcsr & (1 << 18) else "running"
                cause, crashed = None, False
            observation.update(state=state, stop_reason=cause, crashed=crashed)
        except Exception as exc:
            observation["stop_reason"] = f"Core monitoring unavailable: {exc}"
        observation["sample_ended"] = time.monotonic()
        return observation

    def fault_snapshot(self, device: Device) -> dict:
        """Halt a failed core and preserve live and stacked exception context."""
        target = device.attributes.get("target_device")
        profile = _TARGETS.get(target)
        if profile is None:
            raise ValueError(f"Core monitoring does not support {target!r}")
        if self.jlink is None:
            raise RuntimeError("J-Link is not initialized")

        snapshot = {"captured_at": time.time(), "target": target, "registers": {}}
        try:
            self.jlink.halt()
            if not self.jlink.halted():
                raise RuntimeError("Core did not halt")
            # J-Link register names; "R13 (SP)" and "R15 (PC)" are stored as r13/r15.
            names = [f"R{index}" for index in range(13)] + [
                "R13 (SP)", "R14", "R15 (PC)", "XPSR", "MSP", "PSP", "CONTROL"
            ]
            values = self.jlink.register_read_multiple(names)
            snapshot["registers"] = dict(zip((name.split()[0].lower() for name in names), values))

            xpsr = snapshot["registers"]["xpsr"]
            exception = xpsr & 0x1FF
            exc_return = snapshot["registers"]["r14"]
            snapshot["active_exception"] = exception
            snapshot["exc_return"] = exc_return
            if exception:
                cfsr = self.jlink.memory_read32(0xE000ED28, 1)[0]
                hfsr = self.jlink.memory_read32(0xE000ED2C, 1)[0]
                snapshot["cfsr"] = cfsr
                snapshot["hfsr"] = hfsr
                snapshot["fault_causes"] = _fault_causes(cfsr, hfsr, exception)
                stacking_error = cfsr & ((1 << 3) | (1 << 4) | (1 << 11) | (1 << 12))
                if exc_return >> 24 != 0xFF:
                    snapshot["stack_error"] = "LR no longer holds EXC_RETURN; exception frame unknown"
                elif not stacking_error:
                    stack_name = "psp" if exc_return & (1 << 2) else "msp"
                    # R0-xPSR sit at the bottom of both the basic and the
                    # floating-point extended frame.
                    basic_frame = snapshot["registers"][stack_name]
                    ram_start, ram_end = profile["ram"]
                    if ram_start <= basic_frame and basic_frame + 32 <= ram_end:
                        words = self.jlink.memory_read32(basic_frame, 8)
                        if len(words) == 8:
                            snapshot["stack"] = {
                                "pointer": basic_frame,
                                **dict(zip(("r0", "r1", "r2", "r3", "r12", "lr", "pc", "xpsr"), words)),
                            }
                        else:
                            snapshot["stack_error"] = "Incomplete exception frame"
                    else:
                        snapshot["stack_error"] = f"Stack pointer 0x{basic_frame:08X} is outside target RAM"
                else:
                    snapshot["stack_error"] = "Fault status reports a stacking or unstacking error"
        except Exception as exc:
            snapshot["error"] = str(exc)
        return snapshot

    def recover_target(self, device: Device, *, reset: bool = True, timeout_ms: int = 5000) -> dict:
        """Run the target and establish a fresh read-to-clear observation baseline."""
        if not 100 <= timeout_ms <= 30000:
            raise ValueError("timeout_ms must be between 100 and 30000")
        if self.jlink is None:
            raise RuntimeError("J-Link is not initialized")
        started = time.monotonic()
        if reset:
            self.jlink.reset(halt=False)
        elif self.jlink.halted():
            self.jlink.restart()

        deadline = started + timeout_ms / 1000
        last = None
        while time.monotonic() < deadline:
            last = self.core_status(device)
            if last["state"] in ("running", "sleeping") and not last["stop_reason"]:
                baseline = self.core_status(device)
                if baseline["state"] in ("running", "sleeping") and not baseline["stop_reason"]:
                    return {
                        "recovered": True,
                        "reset": reset,
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                        "baseline": baseline,
                    }
            time.sleep(0.05)
        return {
            "recovered": False,
            "reset": reset,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "last_observation": last,
            "error": "Target did not become ready before the recovery deadline",
        }

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
