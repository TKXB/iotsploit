"""Monitor sources: hardware in, :class:`MonitorObservation` out.

A source samples one resource for one plan entry. Two shapes exist:

* **point** sources read the target when asked (a CPU core over SWD): ``begin``
  does nothing and ``end`` samples now;
* **window** sources watch continuously (a UART console, a supply rail): ``begin``
  marks the start of a window and ``end`` summarises what happened since.

The harness calls ``begin`` before a payload and ``end`` after it either way, so
it never needs to know which shape it holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from iotsploit_core.domain.monitoring import MonitorObservation


@dataclass(frozen=True)
class MonitorPlanEntry:
    kind: str
    name: str
    resource: str
    target: str = ""
    target_id: str = ""
    options: Mapping = field(default_factory=dict)


class MonitorSource(Protocol):
    entry: MonitorPlanEntry
    settle_ms: int
    """How long after a payload this source needs before ``end`` is meaningful."""

    def open(self) -> None: ...

    def begin(self) -> None: ...

    def end(self) -> MonitorObservation: ...

    def recover(self, expected: bool) -> dict:
        """Bring the target back to a state worth testing; ``expected`` is a planned reset."""
        ...

    def close(self) -> None:
        """Release the hardware. Safe to call on a source that never opened."""
        ...


def parse_plan(raw) -> list[MonitorPlanEntry]:
    """Shape-check a monitor plan from a request or campaign config."""
    if not isinstance(raw, list):
        raise ValueError("monitors must be a list")
    entries: list[MonitorPlanEntry] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"monitors[{index}] must be an object")
        kind = item.get("kind")
        resource = item.get("resource")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"monitors[{index}].kind is required")
        if not isinstance(resource, str) or not resource:
            raise ValueError(f"monitors[{index}].resource is required")
        options = item.get("options", {})
        if not isinstance(options, dict):
            raise ValueError(f"monitors[{index}].options must be an object")
        entries.append(MonitorPlanEntry(
            kind=kind,
            name=str(item.get("name") or f"{kind}:{index}"),
            resource=resource,
            target=str(item.get("target", "") or ""),
            target_id=str(item.get("target_id", "") or "").strip(),
            options=dict(options),
        ))
    names = [entry.name for entry in entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Monitor names must be unique: {', '.join(duplicates)}")
    resources = [entry.resource for entry in entries]
    shared = sorted({resource for resource in resources if resources.count(resource) > 1})
    if shared:
        raise ValueError(f"A resource can back only one monitor: {', '.join(shared)}")
    return entries


class SourceRegistry:
    """Which monitor kind serves which plan entry. Filled by the composition root."""

    def __init__(self):
        self._kinds: dict = {}

    def register(self, kind) -> None:
        """Add a :class:`~iotsploit_core.core.monitoring.kind.MonitorKind` instance."""
        if kind.KIND in self._kinds:
            raise ValueError(f"Monitor kind {kind.KIND!r} is already registered")
        self._kinds[kind.KIND] = kind

    def kinds(self) -> list[str]:
        return sorted(self._kinds)

    def get(self, name: str):
        kind = self._kinds.get(name)
        if kind is None:
            raise ValueError(f"Unknown monitor kind {name!r}")
        return kind

    def validate(self, entry: MonitorPlanEntry) -> None:
        self.get(entry.kind).validate(entry)

    def create(self, entry: MonitorPlanEntry) -> MonitorSource:
        self.validate(entry)
        return self.get(entry.kind).create(entry)
