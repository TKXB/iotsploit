"""Open monitor plans: leases, sources and guaranteed cleanup, for any kind."""

from __future__ import annotations

import logging

from iotsploit_core.core.monitoring.source import MonitorPlanEntry, MonitorSource, SourceRegistry, parse_plan
from iotsploit_core.domain.monitoring import MonitorObservation
from iotsploit_core.ports.resource_lease import ResourceLeasePort

logger = logging.getLogger(__name__)


class MonitorSession:
    """The open sources of one plan. Closing it releases everything it holds."""

    def __init__(self, lease: ResourceLeasePort, owner: str):
        self._lease = lease
        self.owner = owner
        self.sources: list[MonitorSource] = []
        self._leased: list[str] = []

    def close(self) -> None:
        for source in reversed(self.sources):
            try:
                source.close()
            except Exception as exc:
                logger.warning("Closing monitor %s failed: %s", source.entry.name, exc)
        self.sources = []
        for resource in reversed(self._leased):
            try:
                self._lease.release(resource, self.owner)
            except Exception as exc:
                logger.warning("Releasing %s failed: %s", resource, exc)
        self._leased = []

    def __enter__(self) -> "MonitorSession":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class MonitorService:
    def __init__(self, registry: SourceRegistry, lease: ResourceLeasePort):
        self._registry = registry
        self._lease = lease

    def kinds(self) -> list[str]:
        return self._registry.kinds()

    def describe(self) -> list[dict]:
        """Every kind with its settings schema, for clients that build forms from it."""
        return [self._registry.get(kind).describe() for kind in self._registry.kinds()]

    def policy(self, source: MonitorSource):
        """The campaign policy the source's kind asks for; None means the default."""
        return self._registry.get(source.entry.kind).policy(source)

    def plan(self, raw) -> list[MonitorPlanEntry]:
        """Parse and validate a plan without touching hardware."""
        entries = parse_plan(raw)
        for entry in entries:
            self._registry.validate(entry)
        return entries

    def open(self, entries: list[MonitorPlanEntry], *, owner: str) -> MonitorSession:
        session = MonitorSession(self._lease, owner)
        try:
            for entry in entries:
                self._lease.acquire(entry.resource, owner)
                session._leased.append(entry.resource)
                source = self._registry.create(entry)
                session.sources.append(source)
                source.open()
        except BaseException:
            session.close()
            raise
        return session

    def check(self, entry: MonitorPlanEntry, *, owner: str) -> MonitorObservation:
        """One observation from one monitor, outside any campaign."""
        with self.open([entry], owner=owner) as session:
            source = session.sources[0]
            source.begin()
            return source.end()
