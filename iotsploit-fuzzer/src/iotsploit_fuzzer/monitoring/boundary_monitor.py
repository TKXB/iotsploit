"""The monitor that notices the error boundary moving.

A crash counter reports zero every night once the easy defects are gone, and
a report that says zero every night gets switched off. What does not run out
is *change*: every refactor moves the line between the inputs a parser accepts
and the ones it rejects, and almost every move is unintended. Nothing in the
test suite asserts which ARXML files import or which ASC lines parse. This
ledger is that assertion, and it writes itself.

Three things are worth saying about a campaign, and they are not the same
thing:

``VIOLATION``
    A contract broke. A bug. Fails the run.
``BOUNDARY_MOVED``
    A payload the ledger knows now does something else. Reported, does not
    fail -- somebody has to say whether it was intended.
``NEW_REGION``
    A signature this target has never produced. The corpus grew.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from ..analysis.corpus import CorpusStore, payload_id
from ..analysis.corpus import MAX_EXEMPLARS
from ..analysis.outcome import ACCEPT, REJECT, SKIP, Outcome
from ..core.config import EventType
from ..harnesses.base import HarnessResult
from .monitor import Monitor

logger = logging.getLogger("fuzzer.boundary")

#: Report lines kept per signature. Matches the corpus cap: past the point
#: where a signature stops being retained, repeating it says nothing new.
MAX_REPORTED_PER_SIGNATURE = MAX_EXEMPLARS

Emit = Callable[[EventType, Dict[str, Any]], None]


class BoundaryMonitor(Monitor):
    """Diff every case against the ledger, and decide what the corpus keeps."""

    def __init__(
        self,
        store: CorpusStore,
        campaign: str,
        *,
        generator: Any = None,
        emit: Optional[Emit] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(config)
        self.store = store
        self.campaign = campaign
        self.generator = generator
        self._emit = emit
        self.violations: List[Dict[str, Any]] = []
        self.boundary_moves: List[Dict[str, Any]] = []
        self.new_regions: List[Dict[str, Any]] = []
        self.flaky: List[Dict[str, Any]] = []
        self.kinds: Dict[str, int] = {}
        self.retained = 0
        self._reported: Dict[str, int] = {}

    # -- reporting ---------------------------------------------------------

    def emit(self, event: EventType, data: Dict[str, Any]) -> None:
        if self._emit is not None:
            self._emit(event, data)

    # -- the diff ----------------------------------------------------------

    def process_case(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        super().process_case(idx, payload, result)
        outcome = Outcome.from_signature(
            result.info or "", result.error or "", site=result.site or ""
        )
        self.kinds[outcome.kind] = self.kinds.get(outcome.kind, 0) + 1

        if outcome.kind == SKIP:
            if outcome.reason == "flaky":
                record = self._record(idx, payload, outcome)
                self.flaky.append(record)
                self.emit(EventType.FLAKY_OUTCOME, record)
            return

        identity = payload_id(payload)
        known = self.store.entries.get(identity)
        novel = outcome.signature not in self.store.known_signatures()

        # A payload the ledger already holds, now doing something else. Only
        # meaningful when the ledger's claim was made by this same oracle --
        # a stale store has no comparable claim to make.
        if known is not None and known.signature and known.signature != outcome.signature:
            record = self._record(idx, payload, outcome, was=known.signature)
            self.boundary_moves.append(record)
            self.emit(EventType.BOUNDARY_MOVED, record)
            known.signature = outcome.signature
            known.kind = outcome.kind
        elif novel:
            record = self._record(idx, payload, outcome)
            self.new_regions.append(record)
            self.emit(EventType.NEW_REGION, record)

        if outcome.is_finding:
            record = self._record(idx, payload, outcome)
            if not self._seen_enough(outcome.signature):
                self.violations.append(record)
                self.emit(EventType.CRASH_DETECTED, record)

        # Offered unconditionally: the store's per-signature cap is what
        # bounds the corpus, and keeping a few exemplars of each signature
        # gives the next campaign more than one place to mutate from.
        self.retained += int(self.store.admit(payload, outcome, self.campaign))
        self._retain_edge(payload, outcome)

    def _retain_edge(self, payload: bytes, outcome: Outcome) -> None:
        """Keep both sides when a mutation crossed the accept/reject line.

        One payload does not locate a boundary; a pair that differs by one
        mutation and lands on opposite sides does. Only available when the
        mutator recorded the lineage, and only when the ledger already knows
        what the parent did.
        """
        if outcome.kind not in (ACCEPT, REJECT) or self.generator is None:
            return
        parent = self.generator.parent_of(payload)
        if parent is None:
            return
        entry = self.store.entries.get(payload_id(parent))
        if entry is None or entry.kind not in (ACCEPT, REJECT):
            return
        if entry.kind == outcome.kind:
            return
        self.retained += int(
            self.store.admit(payload, outcome, self.campaign, edge_of=entry.signature)
        )

    def _seen_enough(self, signature: str) -> bool:
        """Whether this signature has already filled its share of the report.

        One systematic defect produces one finding per matching input. A
        report that lists it eight hundred times is a report nobody reads.
        """
        self._reported[signature] = self._reported.get(signature, 0) + 1
        return self._reported[signature] > MAX_REPORTED_PER_SIGNATURE

    def _record(
        self, idx: int, payload: bytes, outcome: Outcome, was: str = ""
    ) -> Dict[str, Any]:
        record = {
            "target": self.store.target.name,
            "campaign": self.campaign,
            "case": idx,
            "payload": payload_id(payload),
            "payload_size": len(payload),
            "signature": outcome.signature,
            "kind": outcome.kind,
            "detail": outcome.detail,
            "site": outcome.site,
        }
        if was:
            record["was"] = was
        return record

    # -- Monitor -----------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats.update(
            {
                "kinds": dict(self.kinds),
                "violations": len(self.violations),
                "boundary_moves": len(self.boundary_moves),
                "new_regions": len(self.new_regions),
                "flaky": len(self.flaky),
                "retained": self.retained,
                "corpus_size": len(self.store.entries),
            }
        )
        return stats
