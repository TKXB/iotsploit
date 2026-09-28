"""CPU monitoring must never turn an uncertain transport result into a pass."""
import json
from types import SimpleNamespace

import pytest

from iotsploit_fuzzer.analysis.logger import TestLogger as CaseLogger
from iotsploit_fuzzer.core.config import CampaignConfig, EventType
from iotsploit_fuzzer.core.orchestrator import Orchestrator
from iotsploit_fuzzer.harnesses.base import HarnessResult
from iotsploit_fuzzer.harnesses.jtag_harness import JtagHarness
from iotsploit_fuzzer.monitoring.monitor import Monitor

pytestmark = pytest.mark.unit


def observation(state="running", exception=0):
    cause = None if state in ("running", "sleeping") else state
    return {"state": state, "stop_reason": cause, "active_exception": exception,
            "crashed": state == "lockup", "registers": {"dhcsr": 0x01000000}}


class UARTHarness:
    def __init__(self, result):
        self.result = result
        self.sent = []

    def execute(self, payload):
        self.sent.append(payload)
        return self.result


@pytest.mark.parametrize("state", ["running", "sleeping"])
def test_clean_core_preserves_protocol_timeout(state):
    inner = UARTHarness(HarnessResult(ok=True, timeout=True, response=None))
    harness = JtagHarness(inner, lambda: observation(state), settle_ms=0)

    result = harness.execute(b"\x22\xf1\x90")

    assert result.timeout and not result.crashed
    assert inner.sent == [b"\x22\xf1\x90"]
    assert result.core_observation["before"]["state"] == state


def test_pre_send_failure_records_unsent_input_and_stops(tmp_path):
    inner = UARTHarness(HarnessResult(ok=True))
    harness = JtagHarness(inner, lambda: observation("unavailable"), settle_ms=0)
    logger = CaseLogger(tmp_path)
    events = []
    generator = SimpleNamespace(seed_corpus=lambda: [b"request"],
                                generate=lambda seeds, total: iter([b"request", b"next"]))
    monitor = Monitor()
    runner = Orchestrator(generator, harness, monitor, logger,
                          CampaignConfig(iterations=2, event_callback=lambda kind, data: events.append(kind)))

    runner.run()

    assert inner.sent == []
    assert monitor.get_stats()["total_cases"] == 0
    assert runner._protocol_type == "UART"
    assert EventType.CAMPAIGN_STOPPED in events
    assert EventType.CAMPAIGN_COMPLETED not in events
    record = json.loads(next(tmp_path.glob("campaign_*.jsonl")).read_text())
    assert record["sent"] is False
    assert record["core_observation"]["state"] == "unavailable"


def test_crash_is_persisted_before_stop_even_with_crash_notification_preference_off(tmp_path):
    samples = iter([observation(), observation("lockup")])
    inner = UARTHarness(HarnessResult(ok=True, timeout=True))
    harness = JtagHarness(inner, lambda: next(samples), settle_ms=0)
    logger = CaseLogger(tmp_path)
    events = []

    def emit(kind, data):
        if kind is EventType.CRASH_DETECTED:
            assert list(tmp_path.glob("crash_*.bin"))
        events.append(kind)

    runner = Orchestrator(
        SimpleNamespace(seed_corpus=lambda: [b"fault"], generate=lambda seeds, total: iter([b"fault", b"next"])),
        harness, Monitor(), logger, CampaignConfig(iterations=2, save_crashes=False, event_callback=emit))

    runner.run()

    assert inner.sent == [b"fault"]
    assert events.index(EventType.TEST_CASE_COMPLETED) < events.index(EventType.CAMPAIGN_STOPPED)
    assert EventType.CRASH_DETECTED in events
    assert EventType.CAMPAIGN_COMPLETED not in events
    record = json.loads(next(tmp_path.glob("campaign_*.jsonl")).read_text())
    assert record["timeout"] and record["crashed"]


@pytest.mark.parametrize("confirmation, crashed", [(observation("fault", 3), True), (observation(), False)])
def test_fault_needs_persistent_exception_evidence(confirmation, crashed):
    samples = iter([observation(), observation("fault", 3), confirmation])
    harness = JtagHarness(UARTHarness(HarnessResult(ok=True)), lambda: next(samples), settle_ms=0)

    result = harness.execute(b"trigger")

    assert result.crashed is crashed
    assert result.stop_reason  # Even uncertain fault evidence stops for inspection.
    assert result.core_observation["confirmation"] == confirmation


def test_repeated_inputs_keep_execution_order_across_campaigns(tmp_path):
    first, second = CaseLogger(tmp_path), CaseLogger(tmp_path)
    result = HarnessResult(ok=True, core_observation=observation(), response=b"ok")

    first.record(1, b"same", result)
    first.record(2, b"same", result)
    second.record(1, b"same", result)

    assert len(list(tmp_path.glob("case_*.bin"))) == 1
    histories = [list(map(json.loads, p.read_text().splitlines())) for p in tmp_path.glob("campaign_*.jsonl")]
    assert sorted(len(h) for h in histories) == [1, 2]
    assert [r["case_index"] for r in max(histories, key=len)] == [1, 2]


def test_recording_failure_prevents_next_send(tmp_path):
    inner = UARTHarness(HarnessResult(ok=True))
    harness = JtagHarness(inner, lambda: observation(), settle_ms=0)
    logger = CaseLogger(tmp_path)
    logger.workdir = tmp_path / "not-created"
    runner = Orchestrator(
        SimpleNamespace(seed_corpus=lambda: [b"one"], generate=lambda seeds, total: iter([b"one", b"two"])),
        harness, Monitor(), logger, CampaignConfig(iterations=2))

    with pytest.raises(FileNotFoundError):
        runner.run()

    assert inner.sent == [b"one"]
    assert not runner.is_running()


@pytest.mark.parametrize("value", [-1, 1001, "20", None])
def test_observation_window_is_bounded(value):
    with pytest.raises(ValueError, match="settle_ms"):
        JtagHarness(UARTHarness(HarnessResult(ok=True)), lambda: observation(), value)


def test_confirmed_fault_is_snapshotted_then_recovered_for_next_case():
    samples = iter(
        [
            observation(),
            observation("fault", 3),
            observation("fault", 3),
            observation(),
            observation(),
        ]
    )
    calls = []
    inner = UARTHarness(HarnessResult(ok=True))
    harness = JtagHarness(
        inner,
        lambda: next(samples),
        settle_ms=0,
        snapshot=lambda: calls.append("snapshot") or {"stack": {"pc": 0x1234}},
        recover=lambda expected: calls.append(("recover", expected)) or {"recovered": True},
        recovery_policy="reset_continue",
    )

    failed = harness.execute(b"fault")
    clean = harness.execute(b"next")

    assert failed.crashed and failed.stop_reason is None
    assert failed.core_observation["snapshot"]["stack"]["pc"] == 0x1234
    assert failed.core_observation["recovery"]["recovered"] is True
    assert calls == ["snapshot", ("recover", False)]
    assert clean.ok and not clean.crashed
    assert inner.sent == [b"fault", b"next"]


def test_expected_reset_waits_for_readiness_without_failing_case():
    samples = iter([observation(), observation("reset")])
    inner = UARTHarness(HarnessResult(ok=True))
    harness = JtagHarness(
        inner,
        lambda: next(samples),
        settle_ms=0,
        recover=lambda expected: {"recovered": expected},
        expected_reset_prefixes=(b"\x11\x01",),
    )

    result = harness.execute(b"\x11\x01\x99")

    assert result.ok and not result.crashed and result.stop_reason is None
    assert result.core_observation["expected_reset"] is True
    assert result.core_observation["recovery"]["recovered"] is True


def test_recovery_limit_stops_campaign():
    samples = iter([observation(), observation("lockup")])
    harness = JtagHarness(
        UARTHarness(HarnessResult(ok=True)),
        lambda: next(samples),
        settle_ms=0,
        recover=lambda expected: {"recovered": True},
        recovery_policy="reset_continue",
        max_recoveries=0,
    )

    result = harness.execute(b"fault")

    assert result.stop_reason == "Recovery limit of 0 reached"
    assert result.core_observation["recovery"]["recovered"] is False
