"""A parse that destroys its process must still produce a result, not an outage.

The controller runs each parse in a subprocess it is willing to lose, because
in-process recovery is not available for the cases that matter: ``MemoryError``
is raised only after the allocation already happened, a signal handler runs
only at a bytecode boundary the interpreter may never reach again, and a native
crash takes the interpreter with it. Each test here is one of those cases, and
each asserts the same thing -- the campaign survived and named what happened.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

from iotsploit_fuzzer.analysis.outcome import ACCEPT, LIMIT, SKIP, TIMEOUT, VIOLATE
from iotsploit_fuzzer.harnesses.parser_harness import ParserHarness
from iotsploit_fuzzer.harnesses.parser_targets import ParseTarget

pytestmark = pytest.mark.unit

HOSTILE = '''
import ctypes, os, subprocess, sys, time

def fine(payload):
    return list(payload)

def oom(payload):
    blob = bytearray()
    while True:
        blob.extend(b"\\x00" * (8 * 1024 * 1024))

def block(payload):
    time.sleep(120)

def segfault(payload):
    ctypes.string_at(1)

def hard_exit(payload):
    os._exit(3)

def leaves_a_child(payload):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    sys.stderr.write("CHILD=%d\\n" % child.pid)
    sys.stderr.flush()
    time.sleep(120)

_calls = []

def unstable(payload):
    """Fails only the first time it is asked, in each fresh process."""
    marker = os.environ["UNSTABLE_MARKER"]
    with open(marker, "a+") as handle:
        handle.seek(0)
        seen = len(handle.read())
        handle.write("x")
    if seen % 2 == 0:
        raise KeyError("intermittent")
    return []
'''


@pytest.fixture
def hostile(tmp_path, monkeypatch):
    """Put a module of badly-behaved targets where a worker can import it."""
    (tmp_path / "hostile_targets.py").write_text(textwrap.dedent(HOSTILE))
    previous = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(tmp_path), previous]).rstrip(os.pathsep))
    return tmp_path


def target(name: str, **overrides) -> ParseTarget:
    settings = {
        "budget_seconds": 3.0,
        "memory_mb": 400,
        "output_kb": 128,
        "declared": (),
    }
    settings.update(overrides)
    return ParseTarget(name=f"hostile.{name}", adapter=f"hostile_targets:{name}", **settings)


def evaluate(name, payload=b"payload", *, repeats=2, **overrides):
    with ParserHarness(target(name, **overrides), repeats=repeats) as harness:
        return harness.evaluate(payload)


def test_a_well_behaved_target_is_accepted(hostile):
    outcome = evaluate("fine", b"abc")

    assert outcome.kind == ACCEPT
    assert outcome.shape.startswith("list[")


@pytest.mark.skipif(
    sys.platform != "linux", reason="the worker's memory cap is RLIMIT_AS, which only Linux enforces"
)
def test_allocating_without_bound_is_a_limit_not_a_dead_host(hostile):
    """The defect that motivated the design: ``parse_target_bits('0-10000000')``
    asked for hundreds of megabytes, and no ``except`` runs early enough."""
    outcome = evaluate("oom")

    assert outcome.kind == LIMIT
    assert outcome.exception == "MemoryError"


def test_a_parse_that_never_returns_is_a_timeout(hostile):
    started = time.time()
    outcome = evaluate("block", repeats=1, budget_seconds=1.0)

    assert outcome.kind == TIMEOUT
    # Two runs of a 1s budget, and bounded: the controller is not waiting on
    # the worker to notice anything itself.
    assert time.time() - started < 20


def test_a_native_crash_is_a_violation_and_names_the_signal(hostile):
    outcome = evaluate("segfault")

    assert outcome.kind == VIOLATE
    if sys.platform == "win32":
        # ctypes turns the access violation into an OSError before the
        # process dies, so there is no signal to name.
        assert "access violation" in outcome.reason
    else:
        assert "SIGSEGV" in outcome.reason


def test_a_target_that_exits_is_a_violation(hostile):
    outcome = evaluate("hard_exit")

    assert outcome.kind == VIOLATE
    assert "exit 3" in outcome.reason


def test_a_process_the_target_started_does_not_survive_the_worker(hostile):
    """A parser that shells out leaves nothing behind when its worker is
    killed, because the whole process group goes."""
    harness = ParserHarness(target("leaves_a_child", budget_seconds=2.0), repeats=1)
    harness._worker = harness._spawn()
    harness._run_once(b"x", harness._worker)
    child = int(harness._worker.stderr_tail(200).split("CHILD=")[1].split()[0])
    harness.close()
    time.sleep(1.0)

    assert subprocess.run(["ps", "-p", str(child)], capture_output=True).returncode != 0


def test_an_outcome_that_does_not_reproduce_is_flaky_rather_than_a_finding(
    hostile, tmp_path, monkeypatch
):
    """Promoting a one-off result would put noise in the ledger for good."""
    monkeypatch.setenv("UNSTABLE_MARKER", str(tmp_path / "marker"))

    outcome = evaluate("unstable", repeats=3)

    assert outcome.kind == SKIP
    assert outcome.reason == "flaky"


def test_a_payload_past_the_limit_is_refused_before_a_worker_sees_it(hostile):
    outcome = evaluate("fine", b"x" * 5000, payload_max_bytes=1024)

    assert outcome.kind == SKIP
    assert "over limit" in outcome.reason


def test_a_batch_worker_is_retired_after_its_quota(hostile):
    """Bounds the blast radius of a leak: without it, a later payload pays for
    an earlier one's allocation and the ledger blames the wrong input."""
    with ParserHarness(target("fine"), quota=3) as harness:
        pids = set()
        for _ in range(9):
            harness.evaluate(b"abc")
            pids.add(harness._worker.proc.pid)

    assert len(pids) == 3
