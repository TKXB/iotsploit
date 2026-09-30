"""Architecture monitors: how to read and decode one CPU architecture's cores."""

from __future__ import annotations

from types import ModuleType

from iotsploit_core.core.monitoring.arch import cortex_m

ARCH_MONITORS: dict[str, ModuleType] = {cortex_m.ARCH: cortex_m}


def arch_monitor(arch: str) -> ModuleType:
    try:
        return ARCH_MONITORS[arch]
    except KeyError:
        raise ValueError(f"No monitor for CPU architecture {arch!r}") from None
