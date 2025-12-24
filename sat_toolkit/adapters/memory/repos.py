from __future__ import annotations

from dataclasses import replace

from sat_toolkit.domain.execution_plan import PluginGroupSpec
from sat_toolkit.domain.plugin import PluginMeta


class MemoryPluginMetaRepository:
    def __init__(self) -> None:
        self._by_name: dict[str, PluginMeta] = {}

    def upsert(self, meta: PluginMeta) -> None:
        self._by_name[meta.name] = meta

    def list_enabled(self) -> list[PluginMeta]:
        return [m for m in self._by_name.values() if m.enabled]

    def disable_missing(self, names: set[str]) -> int:
        updated = 0
        for name, meta in list(self._by_name.items()):
            if name not in names and meta.enabled:
                self._by_name[name] = replace(meta, enabled=False)
                updated += 1
        return updated


class MemoryPluginGroupRepository:
    def __init__(self) -> None:
        self._by_name: dict[str, PluginGroupSpec] = {}

    def list_enabled_groups(self) -> list[PluginGroupSpec]:
        return [g for g in self._by_name.values() if g.enabled]

    def get_group(self, name: str) -> PluginGroupSpec | None:
        return self._by_name.get(name)

    def upsert(self, spec: PluginGroupSpec) -> None:
        self._by_name[spec.name] = spec


