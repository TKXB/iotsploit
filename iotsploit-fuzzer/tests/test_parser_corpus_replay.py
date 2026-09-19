"""Every input the fuzzing loop ever found interesting, checked on every commit.

This is the half of the loop that makes the other half worth running. The
nightly campaign generates and finds; this replays and remembers. Generation
stays out of it deliberately -- a gate that invents new inputs goes red for a
reason the previous run did not have, and a gate that does that gets bypassed.

A failure here is not a flaky test. It means a payload that a parser used to
handle now escapes its declared contract, and the payload that proves it is in
``iotsploit-fuzzer/corpus/<target>/payloads/``.
"""

from __future__ import annotations

import pytest

from iotsploit_fuzzer.analysis.corpus import CorpusStore
from iotsploit_fuzzer.core.parser_campaign import DEFAULT_CORPUS_ROOT, replay
from iotsploit_fuzzer.harnesses.parser_targets import REGISTRY

pytestmark = pytest.mark.integration

RETAINED = sorted(
    name for name in REGISTRY if (DEFAULT_CORPUS_ROOT / name / "ledger.json").exists()
)


def test_the_tracked_corpus_is_present():
    """Guards the arrangement itself. ``artifacts/`` is git-ignored, so a
    corpus written there would leave every clone -- and every CI run --
    replaying nothing while reporting success."""
    assert RETAINED, f"no ledgers under {DEFAULT_CORPUS_ROOT}"


@pytest.mark.parametrize("name", RETAINED)
def test_the_ledger_was_written_by_the_current_oracle(name):
    """A stale ledger means the declared exceptions, the adapter, or the
    signature format changed without a re-baseline, and every diff against it
    from then on is noise."""
    store = CorpusStore(DEFAULT_CORPUS_ROOT, REGISTRY[name])

    assert not store.stale
    assert store.entries


@pytest.mark.parametrize("name", RETAINED)
def test_no_retained_payload_breaks_its_parser(name):
    findings = replay(REGISTRY[name])

    assert findings == []
