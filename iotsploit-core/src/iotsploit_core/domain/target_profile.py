"""What a monitor needs to know about a target chip, as data.

A profile says which CPU architecture a target has, which cores can be watched,
and where its vendor-specific registers live. It is data so that adding a chip
of a known architecture needs no code: see ``core/monitoring/targets``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional


@dataclass(frozen=True)
class ChipId:
    """What a chip's CoreSight ROM table says about it."""

    designer: int
    """JEP106 code as ``continuation << 8 | id``: 0x020 is ST, 0x244 Nordic."""
    part: int


@dataclass(frozen=True)
class IdentifyRule:
    """How to recognise a target from its :class:`ChipId`."""

    designer: int
    parts: tuple[int, ...] = ()
    """ROM-table part numbers this target reports; empty accepts any."""
    register: Optional[int] = None
    value: Optional[int] = None
    """A vendor ID register and what it reads, checked only once the designer matched:
    another vendor's ID address can be plain RAM."""

    def matches(self, chip: ChipId, read32: Callable[[int], int]) -> bool:
        if chip.designer != self.designer or (self.parts and chip.part not in self.parts):
            return False
        if self.register is None:
            return True
        try:
            return read32(self.register) == self.value
        except Exception:
            return False


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
    identify: Optional[IdentifyRule] = None
    """None: the target cannot be recognised on a probe and is only chosen by hand."""

    def core(self, name: str) -> CoreRef:
        for core in self.cores:
            if core.name == name:
                return core
        known = ", ".join(core.name for core in self.cores)
        raise ValueError(f"{self.name} has no core {name!r}; known cores: {known}")
