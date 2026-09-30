"""What a monitor needs to know about a target chip, as data.

A profile says which CPU architecture a target has, which cores can be watched,
and where its vendor-specific registers live. It is data so that adding a chip
of a known architecture needs no code: see ``core/monitoring/targets``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class CoreRef:
    name: str
    """``main`` for single-core parts, ``app``/``net`` for an nRF5340."""


@dataclass(frozen=True)
class TargetProfile:
    name: str
    """The name a debug backend connects with, e.g. ``NRF52840_XXAA``."""
    arch: str
    """Selects the architecture monitor, e.g. ``cortex_m``."""
    vendor: str
    cores: tuple[CoreRef, ...]
    cpuid_part: int
    ram: tuple[int, int]
    """[start, end) of RAM, bounding where a stacked exception frame may be."""
    vendor_registers: Mapping[str, int] = field(default_factory=dict)
    """Extra registers sampled with every observation, by name and address."""

    def core(self, name: str) -> CoreRef:
        for core in self.cores:
            if core.name == name:
                return core
        known = ", ".join(core.name for core in self.cores)
        raise ValueError(f"{self.name} has no core {name!r}; known cores: {known}")
