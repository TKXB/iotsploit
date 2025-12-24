from __future__ import annotations

from typing import Protocol

from sat_toolkit.domain.execution_plan import PluginGroupSpec
from sat_toolkit.domain.plugin import PluginMeta


class PluginMetaRepository(Protocol):
    """Persistence for plugin metadata (enabled/disabled, module path, etc.)."""

    def upsert(self, meta: PluginMeta) -> None: ...

    def list_enabled(self) -> list[PluginMeta]: ...

    def disable_missing(self, names: set[str]) -> int: ...


class PluginGroupRepository(Protocol):
    """Persistence for plugin group orchestration specs."""

    def list_enabled_groups(self) -> list[PluginGroupSpec]: ...

    def get_group(self, name: str) -> PluginGroupSpec | None: ...


