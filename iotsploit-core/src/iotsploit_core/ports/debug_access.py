"""Port for raw access to a target's debug interface (JTAG/SWD).

A backend is a transport: it opens a probe, reads memory and registers, and
halts, resumes or resets the core. It never decides what a register value
means -- decoding lives in ``core/monitoring/arch``, once per architecture, so
every backend for that architecture reads the same registers the same way. That
matters for registers with side effects: Cortex-M DHCSR clears its sticky bits
when read, and only the architecture monitor may read it.

Register names are canonical and lower case (``r0``-``r12``, ``sp``, ``lr``,
``pc``, ``xpsr``, ``msp``, ``psp``, ``control``). A backend maps them to its own
library's spelling.

A backend class also declares ``DEBUG_USB_VENDOR_IDS``, the USB vendor ids of
the probes it drives, so a monitor can pick the backend for a resource key such
as ``usb:1366-1050298903/debug`` without instantiating anything.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class DebugAccess(Protocol):
    def debug_architectures(self) -> frozenset[str]:
        """Architectures whose cores this backend can reach, e.g. ``{"cortex_m"}``."""
        ...

    def attach(self, serial: str, target: str, *, interface: str = "swd") -> None:
        """Open probe ``serial`` and connect to ``target`` without halting it."""
        ...

    def detach(self) -> None:
        """Release the probe. Safe to call when not attached."""
        ...

    def read_mem32(self, address: int, count: int = 1) -> list[int]:
        """Read ``count`` 32-bit words. May return fewer on a failed transfer."""
        ...

    def read_registers(self, names: Sequence[str]) -> list[int]:
        """Read core registers by canonical name. The core must be halted."""
        ...

    def halt(self) -> None: ...

    def is_halted(self) -> bool: ...

    def resume(self) -> None: ...

    def reset_core(self, *, halt: bool = False) -> None: ...


def debug_usb_vendor_ids(backend_class: type) -> tuple[int, ...]:
    return tuple(getattr(backend_class, "DEBUG_USB_VENDOR_IDS", ()))
