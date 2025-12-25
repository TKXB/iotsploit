from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PluginStepSpec:
    sequence: int
    plugin_name: str
    ignore_fail: bool = False
    force_exec: bool = False


@dataclass(frozen=True)
class GroupStepSpec:
    sequence: int
    group_name: str
    ignore_fail: bool = False
    force_exec: bool = False


@dataclass(frozen=True)
class PluginGroupSpec:
    name: str
    enabled: bool = True
    plugin_steps: list[PluginStepSpec] = field(default_factory=list)
    group_steps: list[GroupStepSpec] = field(default_factory=list)


