"""A refactor that moves the accept/reject line must be reported, once.

Nothing in the test suite asserts which ARXML files import or which ASC lines
parse, so a change that quietly narrows a parser passes every gate there is.
The ledger is that missing assertion. These tests hold it to the two things
that make it worth having: it notices a real movement, and it stays quiet
otherwise -- a monitor that cries wolf is switched off, and then the loop is
over whatever the code does.
"""

from __future__ import annotations

import pytest

from iotsploit_fuzzer.analysis.corpus import CorpusStore, payload_id
from iotsploit_fuzzer.analysis.outcome import ACCEPT, REJECT, VIOLATE, Outcome
from iotsploit_fuzzer.core.config import EventType
from iotsploit_fuzzer.harnesses.base import HarnessResult
from iotsploit_fuzzer.harnesses.parser_targets import REGISTRY
from iotsploit_fuzzer.monitoring.boundary_monitor import BoundaryMonitor

pytestmark = pytest.mark.unit

TARGET = REGISTRY["fuzzer.parse_target_bits"]

ACCEPTED = Outcome(kind=ACCEPT, shape="list[few]<num>")
REJECTED = Outcome(kind=REJECT, exception="ValueError", reason="invalid range format")
VIOLATED = Outcome(kind=VIOLATE, exception="KeyError", reason="no such signal")


class Recorder:
    """A stand-in for the Celery/WebSocket callback the UI already listens on."""

    def __init__(self):
        self.events = []

    def __call__(self, event, data):
        self.events.append((event, data))

    def kinds(self, event):
        return [data for name, data in self.events if name is event]


def result_for(outcome: Outcome) -> HarnessResult:
    return HarnessResult(
        ok=outcome.kind in (ACCEPT, REJECT),
        crashed=outcome.is_finding,
        info=outcome.signature,
        error=outcome.detail or None,
        site=outcome.site or None,
    )


@pytest.fixture
def parts(tmp_path):
    store = CorpusStore(tmp_path, TARGET)
    events = Recorder()
    return store, events, BoundaryMonitor(store, "c1", emit=events)


def test_a_first_sighting_is_a_new_region_and_is_retained(parts):
    store, events, monitor = parts

    monitor.process_case(1, b"0-7", result_for(ACCEPTED))

    assert len(events.kinds(EventType.NEW_REGION)) == 1
    assert store.known_signatures() == {ACCEPTED.signature}


def test_a_signature_already_known_is_not_announced_again(parts):
    store, events, monitor = parts

    monitor.process_case(1, b"0-7", result_for(ACCEPTED))
    monitor.process_case(2, b"0-9", result_for(ACCEPTED))

    assert len(events.kinds(EventType.NEW_REGION)) == 1


def test_a_payload_that_changes_what_it_does_is_a_boundary_movement(tmp_path):
    """The whole point: the same input, a different answer, after an edit."""
    store = CorpusStore(tmp_path, TARGET)
    BoundaryMonitor(store, "c1").process_case(1, b"0-7", result_for(ACCEPTED))
    events = Recorder()

    BoundaryMonitor(store, "c2", emit=events).process_case(1, b"0-7", result_for(REJECTED))

    moved = events.kinds(EventType.BOUNDARY_MOVED)
    assert len(moved) == 1
    assert moved[0]["was"] == ACCEPTED.signature
    assert moved[0]["signature"] == REJECTED.signature


def test_a_movement_is_reported_once_and_then_becomes_the_new_record(tmp_path):
    store = CorpusStore(tmp_path, TARGET)
    BoundaryMonitor(store, "c1").process_case(1, b"0-7", result_for(ACCEPTED))
    events = Recorder()
    monitor = BoundaryMonitor(store, "c2", emit=events)

    monitor.process_case(1, b"0-7", result_for(REJECTED))
    monitor.process_case(2, b"0-7", result_for(REJECTED))

    assert len(events.kinds(EventType.BOUNDARY_MOVED)) == 1


def test_an_unchanged_parser_reports_nothing_at_all(tmp_path):
    """The property that decides whether anyone still reads the report in
    month six."""
    store = CorpusStore(tmp_path, TARGET)
    first = BoundaryMonitor(store, "c1")
    for index, payload in enumerate([b"0-7", b"bogus", b"5"]):
        first.process_case(index, payload, result_for(ACCEPTED if index != 1 else REJECTED))
    events = Recorder()

    second = BoundaryMonitor(store, "c2", emit=events)
    for index, payload in enumerate([b"0-7", b"bogus", b"5"]):
        second.process_case(index, payload, result_for(ACCEPTED if index != 1 else REJECTED))

    assert events.events == []
    assert second.get_stats()["boundary_moves"] == 0


def test_a_movement_moves_the_counts_with_the_entry(tmp_path):
    """The entry is not the only thing that records what a payload does.

    ``_counts`` backs ``known_signatures()``, the per-signature cap and the
    saturation ceiling. The monitor used to assign to ``entry.signature``
    directly and leave the counts behind, so the ledger said rejected while
    the count that decides novelty still read accepted.
    """
    store = CorpusStore(tmp_path, TARGET)
    BoundaryMonitor(store, "c1").process_case(1, b"0-7", result_for(ACCEPTED))
    assert store.signature_counts() == {ACCEPTED.signature: 1}

    BoundaryMonitor(store, "c2").process_case(1, b"0-7", result_for(REJECTED))

    entry = store.entries[payload_id(b"0-7")]
    assert entry.signature == REJECTED.signature
    assert entry.kind == REJECTED.kind
    assert store.signature_counts() == {REJECTED.signature: 1}
    assert store.known_signatures() == {REJECTED.signature}


def test_a_signature_nothing_holds_any_more_leaves_the_counts(tmp_path):
    """Zero counts are deleted rather than left at zero, or the saturation
    ceiling would fill up with signatures the corpus no longer has."""
    store = CorpusStore(tmp_path, TARGET)
    BoundaryMonitor(store, "c1").process_case(1, b"0-7", result_for(ACCEPTED))

    BoundaryMonitor(store, "c2").process_case(1, b"0-7", result_for(REJECTED))

    assert ACCEPTED.signature not in store.signature_counts()


def test_a_violation_is_a_finding_and_keeps_the_payload_that_caused_it(parts):
    store, events, monitor = parts

    monitor.process_case(1, b"0-7", result_for(VIOLATED))

    assert monitor.get_stats()["violations"] == 1
    assert dict(store.payloads())
    assert b"0-7" in dict(store.payloads()).values()


def test_one_systematic_defect_does_not_produce_a_thousand_report_lines(parts):
    _store, _events, monitor = parts

    for index in range(200):
        monitor.process_case(index, f"0-{index}".encode(), result_for(VIOLATED))

    assert 0 < monitor.get_stats()["violations"] <= 3


def test_both_sides_are_kept_when_one_mutation_crosses_the_line(tmp_path):
    """A single payload does not locate a boundary; a pair one mutation apart
    does."""

    class Lineage:
        def parent_of(self, payload):
            return b"0-7" if payload == b"0-8" else None

    store = CorpusStore(tmp_path, TARGET)
    monitor = BoundaryMonitor(store, "c1", generator=Lineage())
    monitor.process_case(1, b"0-7", result_for(ACCEPTED))
    for index in range(5):
        monitor.process_case(index + 2, f"pad{index}".encode(), result_for(REJECTED))

    monitor.process_case(9, b"0-8", result_for(REJECTED))

    kept = dict(store.payloads())
    assert b"0-7" in kept.values()
    assert b"0-8" in kept.values()
