from __future__ import annotations

import json
from typing import Any

from django.db import OperationalError

from sat_toolkit.adapters.django.plugins.models import Plugin, PluginGroup, PluginGroupTree, PluginSequence
from iotsploit_core.domain.execution_plan import GroupStepSpec, PluginGroupSpec, PluginStepSpec
from iotsploit_core.domain.plugin import PluginMeta


class DjangoPluginMetaRepository:
    def upsert(self, meta: PluginMeta) -> None:
        try:
            Plugin.objects.update_or_create(
                name=meta.name,
                defaults={
                    "description": meta.description or "",
                    "enabled": bool(meta.enabled),
                    "module_path": meta.module_path,
                    "license": meta.license or "",
                    "author": meta.author or "",
                    "parameters": json.dumps(meta.parameters or {}),
                },
            )
        except OperationalError:
            # DB not ready (migrations not run, etc.) — keep core importable.
            return

    def list_enabled(self) -> list[PluginMeta]:
        try:
            items = Plugin.objects.filter(enabled=True)
        except OperationalError:
            return []

        metas: list[PluginMeta] = []
        for p in items:
            params: dict[str, Any] | None = None
            if p.parameters:
                try:
                    params = json.loads(p.parameters)
                except Exception:
                    params = None
            metas.append(
                PluginMeta(
                    name=p.name,
                    module_path=p.module_path,
                    enabled=p.enabled,
                    description=p.description or "",
                    author=p.author or "",
                    license=p.license or "",
                    parameters=params,
                )
            )
        return metas

    def disable_missing(self, names: set[str]) -> int:
        try:
            qs = Plugin.objects.exclude(name__in=names).filter(enabled=True)
            return int(qs.update(enabled=False))
        except OperationalError:
            return 0


class DjangoPluginGroupRepository:
    def list_enabled_groups(self) -> list[PluginGroupSpec]:
        try:
            groups = PluginGroup.objects.filter(enabled=True)
        except OperationalError:
            return []
        return [self._to_spec(g) for g in groups]

    def get_group(self, name: str) -> PluginGroupSpec | None:
        try:
            g = PluginGroup.objects.get(name=name)
        except (PluginGroup.DoesNotExist, OperationalError):
            return None
        return self._to_spec(g)

    def _to_spec(self, g: PluginGroup) -> PluginGroupSpec:
        # Explicit queries to preserve ordering defined in through models.
        group_steps: list[GroupStepSpec] = []
        plugin_steps: list[PluginStepSpec] = []

        for tree in PluginGroupTree.objects.filter(parent=g).order_by("sequence"):
            group_steps.append(
                GroupStepSpec(
                    sequence=int(tree.sequence),
                    group_name=tree.child.name,
                    ignore_fail=bool(tree.ignore_fail),
                    force_exec=bool(tree.force_exec),
                )
            )

        for seq in PluginSequence.objects.filter(plugingroup=g).order_by("sequence"):
            plugin_steps.append(
                PluginStepSpec(
                    sequence=int(seq.sequence),
                    plugin_name=seq.plugin.name,
                    ignore_fail=bool(seq.ignore_fail),
                )
            )

        return PluginGroupSpec(
            name=g.name,
            enabled=bool(g.enabled),
            plugin_steps=plugin_steps,
            group_steps=group_steps,
        )


