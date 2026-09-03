"""Side-effect-free host prerequisite resolution."""

from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Sequence

from iotsploit_core.core.tool_manager import PathResolver
from iotsploit_core.platforms.capability import Availability, static_compatibility
from iotsploit_core.platforms.consts import LINUX


class PlatformCapabilityResolver:
    """Resolve cheap prerequisites, cached briefly because host state can change."""

    def __init__(self, ttl_seconds: float = 5.0):
        self._ttl_seconds = ttl_seconds
        self._cache: dict[tuple[str, ...], tuple[float, Availability]] = {}
        self._paths = PathResolver()

    def invalidate(self) -> None:
        self._cache.clear()

    def resolve(self, requirements: Sequence[str]) -> Availability:
        key = tuple(requirements)
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < self._ttl_seconds:
            return cached[1]

        result = self._resolve(key)
        self._cache[key] = (now, result)
        return result

    def _resolve(self, requirements: tuple[str, ...]) -> Availability:
        compatibility = static_compatibility(requirements)
        if compatibility is not None and not compatibility.available:
            return compatibility

        for requirement in requirements:
            kind, _, value = requirement.partition(":")
            if kind in {"platform", "module"}:
                continue
            if kind == "binary":
                if not self._paths.resolve_tool_path(value):
                    return Availability(
                        False,
                        f"Required executable '{value}' was not found on PATH.",
                        f"Install '{value}' and ensure it is on PATH.",
                    )
            elif kind == "privileged-helper":
                if not LINUX or not hasattr(socket, "AF_UNIX"):
                    return Availability(False, "The privileged helper is Linux-only.")
                if not Path(value or "/run/iotsploit/priv.sock").exists():
                    return Availability(
                        False,
                        "The privileged helper is not running.",
                        "Run `priv install` and start iotsploit-privd.",
                    )
            elif kind == "wifi":
                if not LINUX:
                    return Availability(False, "The WiFi backend is not implemented on this platform.")
            else:
                return Availability(False, f"Unknown capability requirement: {requirement}")
        return Availability(True)
