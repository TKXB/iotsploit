"""A registry entry is a claim, and a wrong claim is worse than no entry.

The declared exception set *is* the oracle. If it names something that does
not exist, every worker dies before it reaches the parser and the campaign
reports one violation per payload against code it never ran. If it declares
too much, the target can never report anything again. Neither failure is
visible in a campaign's output, so it is checked here instead.
"""

from __future__ import annotations


import pytest

from iotsploit_fuzzer.analysis.outcome import ACCEPT, REJECT
from iotsploit_fuzzer.harnesses.parser_targets import REGISTRY
from iotsploit_fuzzer.harnesses.parser_worker import classify, resolve

pytestmark = pytest.mark.unit

NAMES = sorted(REGISTRY)


@pytest.mark.parametrize("name", NAMES)
def test_every_adapter_resolves(name):
    assert callable(resolve(REGISTRY[name].adapter))


@pytest.mark.parametrize("name", NAMES)
def test_every_declared_name_resolves_to_an_exception(name):
    for declared in REGISTRY[name].declared:
        resolved = resolve(declared)

        assert isinstance(resolved, type) and issubclass(resolved, BaseException)


@pytest.mark.parametrize("name", NAMES)
def test_every_target_has_a_seed_that_actually_reaches_it(name):
    """A registry of seeds that all skip fuzzes nothing, and says nothing when
    it reports zero findings."""
    target = REGISTRY[name]
    adapter = resolve(target.adapter)
    declared = tuple(resolve(d) for d in target.declared)

    kinds = {classify(adapter, declared, seed).kind for seed in target.seeds}

    assert kinds & {ACCEPT, REJECT}


@pytest.mark.parametrize("name", NAMES)
def test_a_targets_limits_are_set(name):
    target = REGISTRY[name]

    assert target.budget_seconds > 0
    assert target.memory_mb > 0
    assert target.output_kb > 0
    assert 0 < target.payload_max_bytes


def test_the_fingerprint_changes_with_the_oracle_and_not_otherwise():
    """What makes an explicit re-baseline possible instead of a silent one."""
    import dataclasses

    target = REGISTRY["fuzzer.parse_target_bits"]
    same = dataclasses.replace(target, name="renamed", seeds=(), budget_seconds=99.0)
    widened = dataclasses.replace(target, declared=target.declared + ("builtins:TypeError",))
    readapted = dataclasses.replace(target, adapter_version="2")

    assert same.fingerprint == target.fingerprint
    assert widened.fingerprint != target.fingerprint
    assert readapted.fingerprint != target.fingerprint


def test_the_registry_covers_the_surfaces_the_survey_ranked_by_exposure():
    """`parser_robustness_fuzzing_proposal.md` section 1, in order. A surface
    dropped from here is a surface nobody fuzzes, silently."""
    assert NAMES == sorted(
        [
            "autosar.inspect_file",
            "canbus.codec_roundtrip",
            "canbus.decode_frame",
            "canbus.from_target",
            "canbus.scan_log",
            "composer.normalize_request",
            "doip.uds_parse",
            "fuzzer.parse_target_bits",
            "someip.sd_parse",
        ]
    )
