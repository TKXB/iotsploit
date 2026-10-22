"""Two mutators, and the default is the one with no dependency.

radamsa reads the shape of its input and finds things a byte-level mutator
reaches only by accident, but it is an external binary that is not a Python
package. Making it the only mutator made a campaign impossible on any machine
nobody had prepared -- CI, the Pi, the Windows target. So it is a choice, and
the properties the loop depends on have to hold in both modes: a campaign
reproduces from its seed, and each mutant knows which payload it came from.
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

import iotsploit_fuzzer.targets.iotsploit  # noqa: F401 - registers the pack
from iotsploit_fuzzer.analysis.corpus import CorpusStore
from iotsploit_fuzzer.generators.corpus_generator import CorpusGenerator
from iotsploit_fuzzer.generators.radamsa_generator import RadamsaGenerator
from iotsploit_fuzzer.harnesses.parser_targets import REGISTRY

pytestmark = pytest.mark.unit

TARGET = REGISTRY["core.as_number"]
SEEDS = [b"0x1000", b"42", b"  7 "]

needs_radamsa = pytest.mark.skipif(
    shutil.which("radamsa") is None, reason="radamsa is optional and is not installed"
)


def generator(radamsa=None, seed=1):
    return CorpusGenerator(CorpusStore(tempfile.mkdtemp(), TARGET), radamsa, seed=seed)


def test_the_default_mutator_needs_nothing_installed():
    """The property that decides whether a campaign can run at all on a
    machine nobody has prepared."""
    produced = list(generator().generate(SEEDS, 200))

    assert len(produced) == 200


def test_the_built_in_mutator_reproduces_from_its_seed():
    first = list(generator(seed=7).generate(SEEDS, 120))
    second = list(generator(seed=7).generate(SEEDS, 120))

    assert first == second


def test_a_different_seed_explores_somewhere_else():
    assert list(generator(seed=7).generate(SEEDS, 120)) != list(
        generator(seed=8).generate(SEEDS, 120)
    )


def test_the_built_in_mutator_records_which_payload_a_mutant_came_from():
    """Edge retention keeps both sides of an accept/reject crossing, which
    needs to know what the far side was."""
    gen = generator()
    mutants = [m for m in gen.generate(SEEDS, 60) if m not in SEEDS]

    parents = [gen.parent_of(m) for m in mutants]

    assert parents and all(p in SEEDS for p in parents)


@needs_radamsa
def test_radamsa_reproduces_and_records_lineage_too():
    """Both modes, the same two properties -- driven one parent at a time
    precisely so radamsa can answer the lineage question."""
    first = list(generator(RadamsaGenerator(seed=3), seed=1).generate(SEEDS, 80))
    second = list(generator(RadamsaGenerator(seed=3), seed=1).generate(SEEDS, 80))

    assert first == second

    gen = generator(RadamsaGenerator(seed=3), seed=1)
    mutants = [m for m in gen.generate(SEEDS, 80) if m not in SEEDS]
    assert mutants and all(gen.parent_of(m) in SEEDS for m in mutants)
