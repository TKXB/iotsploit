"""Sequencing and verdict combination for any number of target monitors."""
import json
from types import SimpleNamespace

import pytest

from iotsploit_fuzzer.analysis.logger import TestLogger as CaseLogger
from iotsploit_fuzzer.core.config import CampaignConfig, EventType
from iotsploit_fuzzer.core.orchestrator import Orchestrator
from iotsploit_fuzzer.harnesses import monitor_set_harness
from iotsploit_fuzzer.harnesses.base import HarnessResult
from iotsploit_fuzzer.harnesses.monitor_set_harness import MonitorSetHarness
from iotsploit_fuzzer.monitoring.monitor import Monitor
from iotsploit_fuzzer.monitoring.target_monitor import MonitorVerdict
from iotsploit_fuzzer.monitors import HealthMonitor, McuCoreMonitor

pytestmark = pytest.mark.unit


def observation(state="running", exception=0, monitor="mcu_core:main"):
    cause = None if state in ("running", "sleeping") else state
    health = {"running": "ok", "sleeping": "ok", "lockup": "fault", "fault": "fault",
              "reset": "reset", "halted": "degraded"}.get(state, "unavailable")
    return {
        "monitor": monitor, "kind": "mcu_core", "resource": "usb:1366-1/debug",
        "target": "NRF52840_XXAA", "window": (0.0, 0.0), "observed_at": 0.0,
        "health": health, "reasons": [cause] if cause else [],
        "detail": {"core": "main", "state": state, "cause": cause, "active_exception": exception,
                   "fault_causes": [], "registers": {"dhcsr": 0x01000000}},
    }


class UARTHarness:
    def __init__(self, result):
        self.result = result
        self.sent = []

    def execute(self, payload):
        self.sent.append(payload)
        return self.result


class ScriptedMonitor:
    """A monitor of another kind, e.g. a UART log, that returns fixed verdicts."""

    def __init__(self, name, before="ok", after="ok", *, reason=None, stop=None, decisive=True, settle_ms=0):
        self.name, self.kind, self.settle_ms = name, "uart", settle_ms
        self._before, self._after = before, after
        self._reason, self._stop, self._decisive = reason, stop, decisive

    def _verdict(self, verdict, stop):
        return MonitorVerdict(self.name, self.kind, verdict, {"monitor": self.name, "kind": self.kind},
                              stop_reason=stop, detected_reason=self._reason if verdict != "ok" else None,
                              decisive=self._decisive)

    def preflight(self):
        return self.before()

    def before(self):
        return self._verdict(self._before, self._stop if self._before != "ok" else None)

    def after(self, payload):
        return self._verdict(self._after, self._stop)


def core(observe):
    return McuCoreMonitor("mcu_core:main", observe, settle_ms=0)


def orchestrator(harness, logger, events, payloads, **config):
    generator = SimpleNamespace(seed_corpus=lambda: payloads[:1], generate=lambda seeds, total: iter(payloads))
    return Orchestrator(generator, harness, Monitor(), logger,
                        CampaignConfig(iterations=len(payloads),
                                       event_callback=lambda kind, data: events.append((kind, data)),
                                       **config))


def test_pre_send_failure_records_unsent_input_and_stops(tmp_path):
    inner = UARTHarness(HarnessResult(ok=True))
    harness = MonitorSetHarness(inner, [core(lambda: observation("unavailable"))])
    events = []
    runner = orchestrator(harness, CaseLogger(tmp_path), events, [b"request", b"next"])

    runner.run()

    kinds = [kind for kind, _ in events]
    assert inner.sent == []
    assert runner._protocol_type == "UART"
    assert EventType.CAMPAIGN_STOPPED in kinds
    assert EventType.CAMPAIGN_COMPLETED not in kinds
    status = next(data for kind, data in events if kind is EventType.MONITOR_STATUS)
    assert status["monitor_verdicts"][0]["observation"]["detail"]["state"] == "unavailable"
    record = json.loads(next(tmp_path.glob("campaign_*.jsonl")).read_text())
    assert record["sent"] is False
    assert record["monitor_verdicts"][0]["observation"]["detail"]["state"] == "unavailable"


def test_crash_is_persisted_before_stop_even_with_crash_notification_preference_off(tmp_path):
    samples = iter([observation(), observation("lockup")])
    inner = UARTHarness(HarnessResult(ok=True, timeout=True))
    harness = MonitorSetHarness(inner, [core(lambda: next(samples))])
    events = []

    def emit(kind, data):
        if kind is EventType.CRASH_DETECTED:
            assert list(tmp_path.glob("crash_*.bin"))
        events.append(kind)

    generator = SimpleNamespace(seed_corpus=lambda: [b"fault"], generate=lambda seeds, total: iter([b"fault", b"next"]))
    runner = Orchestrator(generator, harness, Monitor(), CaseLogger(tmp_path),
                          CampaignConfig(iterations=2, save_crashes=False, event_callback=emit))

    runner.run()

    assert inner.sent == [b"fault"]
    assert events.index(EventType.TEST_CASE_COMPLETED) < events.index(EventType.CAMPAIGN_STOPPED)
    assert EventType.CRASH_DETECTED in events
    assert EventType.CAMPAIGN_COMPLETED not in events
    record = json.loads(next(tmp_path.glob("campaign_*.jsonl")).read_text())
    assert record["timeout"] and record["crashed"]


def test_repeated_inputs_keep_execution_order_across_campaigns(tmp_path):
    first, second = CaseLogger(tmp_path), CaseLogger(tmp_path)
    result = HarnessResult(ok=True, monitor_verdicts=[{"observation": observation()}], response=b"ok")

    first.record(1, b"same", result)
    first.record(2, b"same", result)
    second.record(1, b"same", result)

    assert len(list(tmp_path.glob("case_*.bin"))) == 1
    histories = [list(map(json.loads, p.read_text().splitlines())) for p in tmp_path.glob("campaign_*.jsonl")]
    assert sorted(len(h) for h in histories) == [1, 2]
    assert [r["case_index"] for r in max(histories, key=len)] == [1, 2]


def test_recording_failure_prevents_next_send(tmp_path):
    inner = UARTHarness(HarnessResult(ok=True))
    harness = MonitorSetHarness(inner, [core(lambda: observation())])
    logger = CaseLogger(tmp_path)
    logger.workdir = tmp_path / "not-created"
    runner = orchestrator(harness, logger, [], [b"one", b"two"])

    with pytest.raises(FileNotFoundError):
        runner.run()

    assert inner.sent == [b"one"]
    assert not runner.is_running()


def test_worst_decisive_verdict_decides_and_names_its_monitor():
    samples = iter([observation(), observation("lockup")])
    harness = MonitorSetHarness(UARTHarness(HarnessResult(ok=True)),
                                [ScriptedMonitor("uart:console"), core(lambda: next(samples))])

    result = harness.execute(b"x")

    assert result.crashed and not result.ok
    assert result.stop_reason == "mcu_core:main: lockup"
    assert [verdict["verdict"] for verdict in result.monitor_verdicts] == ["ok", "crash"]


def test_corroborating_evidence_never_fails_or_stops_a_case():
    harness = MonitorSetHarness(
        UARTHarness(HarnessResult(ok=True)),
        [core(lambda: observation()),
         ScriptedMonitor("uart:console", after="crash", reason="panic line", stop="panic line", decisive=False)],
    )

    result = harness.execute(b"x")

    assert result.ok and not result.crashed and result.stop_reason is None
    assert result.monitor_verdicts[1]["verdict"] == "crash"
    assert "uart:console: panic line" in result.info


def test_any_unfit_monitor_blocks_the_send():
    inner = UARTHarness(HarnessResult(ok=True))
    harness = MonitorSetHarness(inner, [core(lambda: observation()),
                                        ScriptedMonitor("ble:dut", before="hang", reason="no adverts",
                                                        stop="no adverts")])

    result = harness.execute(b"x")

    assert inner.sent == [] and result.sent is False
    assert result.stop_reason == "ble:dut: no adverts"
    assert len(result.monitor_verdicts) == 2


def test_settle_waits_for_the_slowest_monitor(monkeypatch):
    slept = []
    monkeypatch.setattr(monitor_set_harness.time, "sleep", slept.append)
    harness = MonitorSetHarness(UARTHarness(HarnessResult(ok=True)),
                                [ScriptedMonitor("a", settle_ms=5), ScriptedMonitor("b", settle_ms=40)])

    harness.execute(b"x")

    assert slept == [0.04]


def test_monitor_names_must_be_unique_and_present():
    with pytest.raises(ValueError, match="at least one"):
        MonitorSetHarness(UARTHarness(HarnessResult(ok=True)), [])
    with pytest.raises(ValueError, match="unique"):
        MonitorSetHarness(UARTHarness(HarnessResult(ok=True)), [ScriptedMonitor("a"), ScriptedMonitor("a")])


def test_unknown_verdict_is_rejected():
    with pytest.raises(ValueError, match="verdict"):
        MonitorVerdict("m", "uart", "exploded", {})


@pytest.mark.parametrize("health, verdict, stops", [
    ("ok", "ok", False),
    ("degraded", "inconclusive", False),
    ("fault", "crash", True),
    ("reset", "inconclusive", True),
    ("unavailable", "inconclusive", True),
])
def test_default_policy_judges_any_kind_by_health(health, verdict, stops):
    reasons = [] if health == "ok" else ["no heartbeat"]
    monitor = HealthMonitor("beat", "heartbeat", lambda: {"health": health, "reasons": reasons})

    result = monitor.after(b"payload")

    assert result.verdict == verdict
    assert (result.stop_reason == "no heartbeat") is stops
    assert result.detected_reason == (reasons[0] if reasons else None)


def test_healthy_monitor_preserves_transport_stop_and_evidence():
    evidence = {"protocol": "usbtmc", "outcome": "protocol_failure"}
    inner = UARTHarness(HarnessResult(ok=False, error="Bad USB header",
                                    stop_reason="Bad USB header", evidence=evidence))
    result = MonitorSetHarness(inner, [ScriptedMonitor("board")]).execute(b"bad")
    assert result.stop_reason == "Bad USB header"
    assert not result.ok and not result.crashed
    assert result.evidence == evidence
