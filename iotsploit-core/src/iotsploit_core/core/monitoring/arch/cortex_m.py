"""Reading and decoding an Arm Cortex-M core through any debug backend.

This is the only code that reads DHCSR. Its S_RESET_ST and S_RETIRE_ST bits
clear when read, so every extra read loses evidence: one sample reads it once.
"""

from __future__ import annotations

import time
from typing import Optional

from iotsploit_core.domain.monitoring import McuCoreDetail
from iotsploit_core.domain.target_profile import TargetProfile
from iotsploit_core.ports.debug_access import DebugAccess

ARCH = "cortex_m"

CPUID = 0xE000ED00
ICSR = 0xE000ED04
CFSR = 0xE000ED28
HFSR = 0xE000ED2C
MMFAR = 0xE000ED34
BFAR = 0xE000ED38
DHCSR = 0xE000EDF0

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
FAULT_EXCEPTIONS = {3: "HardFault", 4: "MemManage", 5: "BusFault", 6: "UsageFault"}

SNAPSHOT_REGISTERS = [f"r{index}" for index in range(13)] + [
    "sp", "lr", "pc", "xpsr", "msp", "psp", "control",
]


def fault_causes(cfsr: int, hfsr: int, exception: int) -> list[str]:
    causes = [name for bit, name in _CFSR_BITS.items() if cfsr & (1 << bit)]
    causes.extend(name for bit, name in _HFSR_BITS.items() if hfsr & (1 << bit))
    if not causes and exception in FAULT_EXCEPTIONS:
        causes.append(f"active {FAULT_EXCEPTIONS[exception]}")
    return causes


def _read_one(access: DebugAccess, name: str, address: int) -> int:
    words = access.read_mem32(address, 1)
    if len(words) != 1:
        raise RuntimeError(f"Incomplete {name} read")
    return words[0]


def sample(access: DebugAccess, profile: TargetProfile, *, core: str) -> McuCoreDetail:
    """Classify the core without halting it."""
    registers: dict[str, int] = {}
    detail: McuCoreDetail = {
        "core": core, "state": "unavailable", "cause": None, "fault_causes": [],
        "active_exception": None, "retired": None, "reset_observed": None,
        "registers": registers, "arch": ARCH, "sample_started": time.monotonic(),
        "sample_ended": 0.0,
    }
    try:
        for name, address in (
            ("cpuid", CPUID), ("dhcsr", DHCSR), ("icsr", ICSR), ("cfsr", CFSR), ("hfsr", HFSR),
            *profile.vendor_registers.items(),
        ):
            registers[name] = _read_one(access, name, address)
        part = (registers["cpuid"] >> 4) & 0xFFF
        if part != profile.cpuid_part:
            raise RuntimeError(
                f"Expected CPUID part 0x{profile.cpuid_part:03X}, "
                f"read 0x{registers['cpuid']:08X}; verify target and debug access"
            )
        cfsr = registers["cfsr"]
        for name, address, valid in (("mmfar", MMFAR, cfsr & (1 << 7)), ("bfar", BFAR, cfsr & (1 << 15))):
            if valid:
                registers[name] = _read_one(access, name, address)
        dhcsr = registers["dhcsr"]
        exception = registers["icsr"] & 0x1FF
        causes = fault_causes(cfsr, registers["hfsr"], exception)
        detail.update(retired=bool(dhcsr & (1 << 24)), reset_observed=bool(dhcsr & (1 << 25)),
                      active_exception=exception, fault_causes=causes)
        # An active fault handler outranks a halt: connecting to a locked-up
        # core halts it inside its HardFault. Fault status bits with no active
        # handler describe a fault firmware already handled; they stay in
        # fault_causes as evidence.
        if dhcsr & (1 << 19):
            state, cause = "lockup", "CPU lockup"
        elif exception in FAULT_EXCEPTIONS:
            state, cause = "fault", f"Fault evidence observed: {', '.join(causes) or 'unknown fault'}"
        elif dhcsr & (1 << 17):
            state, cause = "halted", "Unexpected debug halt"
        elif dhcsr & (1 << 25):
            state, cause = "reset", "Reset observed; cause and input attribution unconfirmed"
        else:
            state, cause = ("sleeping" if dhcsr & (1 << 18) else "running"), None
        detail.update(state=state, cause=cause)
    except Exception as exc:
        detail["cause"] = f"Core monitoring unavailable: {exc}"
    detail["sample_ended"] = time.monotonic()
    return detail


def fault_snapshot(access: DebugAccess, profile: TargetProfile) -> dict:
    """Halt a failed core and preserve live and stacked exception context."""
    snapshot: dict = {"captured_at": time.time(), "target": profile.name, "registers": {}}
    try:
        access.halt()
        if not access.is_halted():
            raise RuntimeError("Core did not halt")
        values = access.read_registers(SNAPSHOT_REGISTERS)
        registers = dict(zip(SNAPSHOT_REGISTERS, values))
        snapshot["registers"] = registers
        exception = registers["xpsr"] & 0x1FF
        exc_return = registers["lr"]
        snapshot["active_exception"] = exception
        snapshot["exc_return"] = exc_return
        if exception:
            cfsr = _read_one(access, "cfsr", CFSR)
            hfsr = _read_one(access, "hfsr", HFSR)
            snapshot.update(cfsr=cfsr, hfsr=hfsr, fault_causes=fault_causes(cfsr, hfsr, exception))
            snapshot.update(_stacked_frame(access, profile, registers, cfsr, exc_return))
    except Exception as exc:
        snapshot["error"] = str(exc)
    return snapshot


def _stacked_frame(access: DebugAccess, profile: TargetProfile, registers: dict,
                   cfsr: int, exc_return: int) -> dict:
    stacking_error = cfsr & ((1 << 3) | (1 << 4) | (1 << 11) | (1 << 12))
    if exc_return >> 24 != 0xFF:
        return {"stack_error": "LR no longer holds EXC_RETURN; exception frame unknown"}
    if stacking_error:
        return {"stack_error": "Fault status reports a stacking or unstacking error"}
    # R0-xPSR sit at the bottom of both the basic and the floating-point
    # extended frame.
    pointer: Optional[int] = registers["psp" if exc_return & (1 << 2) else "msp"]
    ram_start, ram_end = profile.ram
    if not (ram_start <= pointer and pointer + 32 <= ram_end):
        return {"stack_error": f"Stack pointer 0x{pointer:08X} is outside target RAM"}
    words = access.read_mem32(pointer, 8)
    if len(words) != 8:
        return {"stack_error": "Incomplete exception frame"}
    return {"stack": {"pointer": pointer,
                      **dict(zip(("r0", "r1", "r2", "r3", "r12", "lr", "pc", "xpsr"), words))}}
