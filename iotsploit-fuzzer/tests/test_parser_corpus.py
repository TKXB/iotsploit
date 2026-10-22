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
import zipfile

import pytest

from iotsploit_fuzzer.analysis.corpus import (
    LedgerEntry,
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


def test_the_smallest_example_of_a_signature_is_the_one_kept(store):
    """Bounds the corpus in bytes, not only in entries.

    radamsa's repetition mutations grow their input, and an entry-only cap
    lets a grown mutant be retained, become the next generation's parent and
    grow again -- 61 bytes to 567 KB in eight generations, measured. It also
    hands triage the smallest reproduction rather than whichever arrived
    first."""
    for n in range(MAX_EXEMPLARS):
        store.admit(b"x" * (500 + n), ACCEPTED, "c1")

    assert store.admit(b"tiny", ACCEPTED, "c2") is True

    kept = sorted(len(p) for _, p in store.payloads())
    assert kept[0] == 4
    assert len(kept) == MAX_EXEMPLARS


def test_a_larger_example_of_a_known_signature_is_turned_away(store):
    for n in range(MAX_EXEMPLARS):
        store.admit(b"x" * (10 + n), ACCEPTED, "c1")

    assert store.admit(b"x" * 5000, ACCEPTED, "c2") is False
    assert len(store.entries) == MAX_EXEMPLARS


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


def test_payloads_live_in_one_archive_per_target(store, tmp_path):
    """A thousand inputs of a hundred bytes each, stored one file apiece, was
    74% of the repository's tracked file count for 1% of its bytes -- and a
    4 KB block each, turning 1.1 MB of payloads into 9.4 MB on disk."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.admit(b"bogus", REJECTED, "c1")
    store.save()

    assert store.archive_path.exists()
    assert not list(store.root.glob("payloads/*.bin"))
    assert dict(CorpusStore(tmp_path, TARGET).payloads()) == {
        payload_id(b"0-7"): b"0-7",
        payload_id(b"bogus"): b"bogus",
    }


def test_a_corpus_of_loose_files_migrates_itself(store, tmp_path):
    """So an existing corpus does not have to be rebuilt to move house."""
    loose = store.legacy_dir
    loose.mkdir(parents=True, exist_ok=True)
    (loose / f"{payload_id(b'0-7')}.bin").write_bytes(b"0-7")
    reopened = CorpusStore(tmp_path, TARGET)
    reopened.entries[payload_id(b"0-7")] = LedgerEntry(
        signature=ACCEPTED.signature, kind=ACCEPTED.kind, first_seen="old"
    )

    reopened.save()

    assert not loose.exists()
    assert dict(CorpusStore(tmp_path, TARGET).payloads())[payload_id(b"0-7")] == b"0-7"


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


def test_a_campaign_that_learned_nothing_leaves_the_ledger_alone(store, tmp_path):
    """The normal night. Rewriting the timestamp anyway put every target's
    ledger in every diff, which buries the one line saying a boundary moved
    -- and that line is what tracking the corpus in git is for."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()
    before = store.ledger_path.read_bytes()

    CorpusStore(tmp_path, TARGET).save()

    assert store.ledger_path.read_bytes() == before


def test_a_ledger_naming_a_payload_the_archive_lacks_is_damaged(store, tmp_path):
    """The case that has to fail closed.

    The ledger and the archive are two renames; a kill between them leaves a
    mixed pair. ``payloads()`` would skip what it cannot find, so the replay
    would check fewer inputs than the ledger claims and still report success
    -- a green gate that covered less than it says."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.admit(b"bogus", REJECTED, "c1")
    store.save()
    with zipfile.ZipFile(store.archive_path, "w"):
        pass

    reopened = CorpusStore(tmp_path, TARGET)

    assert "not in the archive" in reopened.damaged


def test_an_unreadable_archive_is_not_an_empty_corpus(store, tmp_path):
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()
    store.archive_path.write_bytes(b"not a zip at all")

    reopened = CorpusStore(tmp_path, TARGET)

    assert "cannot be read" in reopened.damaged


def test_a_payload_the_ledger_does_not_name_is_only_noise(store, tmp_path):
    """The harmless direction: it costs space and nothing else, so it is
    reported and ignored rather than failing a run."""
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()
    with zipfile.ZipFile(store.archive_path, "a") as archive:
        archive.writestr("deadbeefdeadbeef.bin", b"orphan")

    reopened = CorpusStore(tmp_path, TARGET)

    assert reopened.damaged == ""
    assert len(list(reopened.payloads())) == 1


def test_a_healthy_corpus_is_not_damaged(store, tmp_path):
    store.admit(b"0-7", ACCEPTED, "c1")
    store.save()

    assert CorpusStore(tmp_path, TARGET).damaged == ""


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
