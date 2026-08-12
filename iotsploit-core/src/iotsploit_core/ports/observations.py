"""Ports for recording what a plugin discovered.

Two protocols with deliberately separate responsibilities:

``ObservationProducer`` is implemented by plugins that have durable findings to
record. It is opt-in: a plugin that does not implement it produces no
observations. This is kept apart from ``ExploitResult.data``, which stays the
execution-response contract and may carry raw output, commands and timings that
must never be persisted.

``ObservationSink`` is implemented by the persistence adapter and injected from
the composition root, so core never imports Django.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable

from iotsploit_core.domain.observation import Fact, ObservationBatch, ObservationScope, StartedScan


@runtime_checkable
class ObservationProducer(Protocol):
    """A plugin that records durable facts about a target."""

    def observation_scopes(self, target: Any, parameters: Optional[dict]) -> List[ObservationScope]:
        """Declare the scopes this run will cover, before it runs.

        Declaring up front is what allows a crash to be recorded as a failed
        scan rather than as a scan that never happened.
        """
        ...

    def observation_batches(self, result: Any) -> List[ObservationBatch]:
        """Return one batch per declared scope, after the run.

        A scope with no findings still returns a batch: an empty complete
        snapshot is how "nothing is exposed any more" gets recorded.
        """
        ...


@runtime_checkable
class ObservationSink(Protocol):
    """Durable storage for scan lifecycle and facts."""

    def start_scans(
        self,
        *,
        run_id: str,
        target_id: str,
        source: str,
        scopes: List[ObservationScope],
    ) -> List[StartedScan]:
        ...

    def complete_scan(self, scan_id: str, facts: List[Fact], *, is_complete: bool = True) -> int:
        ...

    def fail_scan(self, scan_id: str, error_summary: Optional[str] = None) -> None:
        ...
