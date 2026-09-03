"""Host-local capability contracts used by plugin and driver managers."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Protocol, Sequence

from iotsploit_core.platforms.consts import DARWIN, LINUX, WINDOWS


@dataclass(frozen=True)
class Availability:
    available: bool
    reason: str = ""
    hint: str = ""


class CapabilityResolver(Protocol):
    def resolve(self, requirements: Sequence[str]) -> Availability: ...


_PLATFORMS = {"linux": LINUX, "darwin": DARWIN, "windows": WINDOWS}
_PLATFORM_NAMES = {"linux": "Linux", "darwin": "macOS", "windows": "Windows"}
_MODULE_HINTS = {
    "gi": "Install PyGObject and the NetworkManager typelib on Linux.",
    "pyudev": "pyudev is available on Linux only.",
}


def static_compatibility(requirements: Sequence[str]) -> Availability | None:
    """Resolve OS and import requirements without importing optional modules."""
    deferred = False
    for requirement in requirements:
        kind, separator, value = requirement.partition(":")
        if not separator and kind in {"privileged-helper", "wifi"}:
            deferred = True
            continue
        if not separator or not value:
            return Availability(False, f"Invalid capability requirement: {requirement}")
        if kind == "platform":
            supported = _PLATFORMS.get(value)
            if supported is None:
                return Availability(False, f"Unknown platform requirement: {value}")
            if not supported:
                return Availability(False, f"This feature requires {_PLATFORM_NAMES[value]}.")
        elif kind == "module":
            try:
                importable = importlib.util.find_spec(value) is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                importable = False
            if not importable:
                return Availability(
                    False,
                    f"Python module '{value}' is not installed.",
                    _MODULE_HINTS.get(value, f"Install the Python package that provides '{value}'."),
                )
        else:
            deferred = True
    return None if deferred else Availability(True)
