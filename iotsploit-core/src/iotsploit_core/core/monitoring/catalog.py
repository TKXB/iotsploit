"""Target profiles loaded from the data files in ``targets/``."""

from __future__ import annotations

import json
from importlib import resources
from typing import Iterable

from iotsploit_core.domain.target_profile import CoreRef, TargetProfile


def _int(value) -> int:
    return value if isinstance(value, int) else int(str(value), 0)


def profile_from_dict(data: dict) -> TargetProfile:
    start, end = (_int(value) for value in data["ram"])
    return TargetProfile(
        name=data["name"],
        arch=data["arch"],
        vendor=data["vendor"],
        cores=tuple(CoreRef(name) for name in data["cores"]),
        cpuid_part=_int(data["cpuid_part"]),
        ram=(start, end),
        vendor_registers={name: _int(address) for name, address in data.get("vendor_registers", {}).items()},
    )


class TargetCatalog:
    def __init__(self, profiles: Iterable[TargetProfile]):
        self._profiles: dict[str, TargetProfile] = {}
        for profile in profiles:
            if profile.name in self._profiles:
                raise ValueError(f"Target {profile.name} is defined twice")
            if not profile.cores:
                raise ValueError(f"Target {profile.name} lists no cores")
            self._profiles[profile.name] = profile

    @classmethod
    def load_default(cls) -> "TargetCatalog":
        profiles = []
        for item in sorted(resources.files(__package__).joinpath("targets").iterdir(), key=lambda p: p.name):
            if item.name.endswith(".json"):
                profiles.extend(profile_from_dict(entry) for entry in json.loads(item.read_text())["targets"])
        return cls(profiles)

    def get(self, name: str) -> TargetProfile:
        profile = self._profiles.get(name)
        if profile is None:
            raise ValueError("Core monitor target is not supported")
        return profile

    def names(self) -> list[str]:
        return sorted(self._profiles)
