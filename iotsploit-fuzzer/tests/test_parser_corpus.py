"""The corpus must stay bounded, and the ledger must survive being interrupted.

Two failure modes this guards against, both of which quietly destroy the loop
rather than breaking it loudly:

* A retention rule that admits everything turns the corpus into the same
  graveyard ``artifacts/`` already is -- thousands of files that all prove the
  same point, and a gate replay too slow to keep.
* A ledger written non-atomically, or compared across a changed oracle, either
  loses months of boundary history to one interrupted run or reports every
  entry as a movement nobody caused.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from iotsploit_fuzzer.analysis.corpus import (
    MAX_EDGE_EXEMPLARS,
    MAX_EXEMPLARS,
    MAX_PER_SIGNATURE,
    MAX_SIGNATURES,
    CorpusStore,
    payload_id,
)
from iotsploit_fuzzer.analysis.outcome import ACCEPT, REJECT, Outcome
from iotsploit_fuzzer.harnesses.parser_targets import REGISTRY

pytestmark = pytest.mark.unit

TARGET = REGISTRY["fuzzer.parse_target_bits"]

ACCEPTED = Outcome(kind=ACCEPT, shape="list[few]<num>")
REJECTED = Outcome(kind=REJECT, exception="ValueError", reason="invalid range format")


@pytest.fixture
def store(tmp_path):
    return CorpusStore(tmp_path, TARGET)


def test_a_payload_is_identified_by_content_not_by_position():
    """The bug that made five campaigns overwrite each other in one namespace."""
    assert payload_id(b"0-7") == payload_id(b"0-7")
    assert payload_id(b"0-7") != payload_id(b"0-8")


def test_one_signature_cannot_fill_the_corpus(store):
    admitted = sum(
        store.admit(f"0-{n}".encode(), ACCEPTED, "c1") for n in range(50)
    )

    assert admitted == MAX_EXEMPLARS


def test_an_edge_is_kept_past_the_signature_cap_but_not_without_limit(store):
    """Both sides of a crossing are worth keeping; every crossing is not."""
    for n in range(50):
        store.admit(f"0-{n}".encode(), ACCEPTED, "c1")
    before = len(store.entries)

    admitted = sum(
        store.admit(f"edge-{n}".encode(), ACCEPTED, "c1", edge_of=REJECTED.signature)
        for n in range(20)
    )

    assert admitted == MAX_EDGE_EXEMPLARS
    assert len(store.entries) == before + MAX_EDGE_EXEMPLARS


def test_a_signature_reachable_from_many_parents_still_has_a_ceiling(store):
    """Edges are capped per pair, so without an absolute ceiling a popular
    signature accumulates one exemplar per distinct parent and escapes both."""
    for n in range(40):
        store.admit(f"p{n}".encode(), ACCEPTED, "c1", edge_of=f"reject|E|reason-{n}||")

    assert len(store.entries) <= MAX_PER_SIGNATURE


def test_a_target_with_too_many_behaviours_stops_rather_than_grows(store):
    """The per-signature caps bound payloads per behaviour, not the number of
    behaviours. A result shape with six bucketed fields has a combinatorially
    large space, so something has to stop -- visibly, because reaching this
    means the shape is too fine-grained to be a boundary."""
    for n in range(MAX_SIGNATURES + 50):
        store.admit(f"p{n}".encode(), Outcome(kind=ACCEPT, shape=f"list[{n}]"), "c1")

    assert store.saturated
    assert len(store.signature_counts()) == MAX_SIGNATURES


def test_a_known_payload_keeps_the_history_that_a_diff_is_made_against(store):
    store.admit(b"0-7", ACCEPTED, "c1")

    assert store.admit(b"0-7", REJECTED, "c2") is False
    assert store.entries[payload_id(b"0-7")].signature == ACCEPTED.signature
    assert store.entries[payload_id(b"0-7")].first_seen == "c1"


def test_a_ledger_survives_a_reload(store, tmp_path):
    store.admit(b"0-7", ACCEPTED, "c1")
    store.admit(b"bogus", REJECTED, "c1")
    store.save()

    reloaded = CorpusStore(tmp_path, TARGET)

    assert not reloaded.stale
    assert reloaded.known_signatures() == {ACCEPTED.signature, REJECTED.signature}
    assert dict(reloaded.payloads())[payload_id(b"0-7")] == b"0-7"


def test_a_half_written_ledger_is_never_visible(store, tmp_path):
    """Written to a temporary name and renamed, so an interrupted nightly run
    leaves the previous ledger valid rather than a truncated one."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()
    first = store.ledger_path.read_bytes()

    store.admit(b"bogus", REJECTED, "c2")
    store.save()

    assert json.loads(first)["entries"]
    assert len(json.loads(store.ledger_path.read_bytes())["entries"]) == 2
    assert not list(store.root.glob("*.tmp-*"))


def test_a_changed_oracle_makes_the_ledger_stale_rather_than_wrong(store, tmp_path):
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()

    widened = dataclasses.replace(TARGET, declared=TARGET.declared + ("builtins:TypeError",))
    reloaded = CorpusStore(tmp_path, widened)

    assert reloaded.stale


def test_a_rebaseline_drops_the_claims_and_keeps_the_payloads(store, tmp_path):
    """The payloads are the expensive part and are still interesting inputs.
    Only the claim about what they do is dropped, because a different oracle
    made it."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()
    reloaded = CorpusStore(tmp_path, dataclasses.replace(TARGET, adapter_version="99"))

    reloaded.rebaseline()

    assert not reloaded.stale
    assert reloaded.known_signatures() == set()
    assert dict(reloaded.payloads())[payload_id(b"0-7")] == b"0-7"


def test_the_campaign_after_a_rebaseline_re_derives_what_a_payload_does(store, tmp_path):
    """Without this the ledger never recovers: nothing re-records a signature
    for a payload already held, so every case reads as novel for ever."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()
    reloaded = CorpusStore(tmp_path, dataclasses.replace(TARGET, adapter_version="99"))
    reloaded.rebaseline()

    reloaded.admit(b"0-7", REJECTED, "c2")

    assert reloaded.known_signatures() == {REJECTED.signature}
    assert reloaded.entries[payload_id(b"0-7")].first_seen == "c1"
