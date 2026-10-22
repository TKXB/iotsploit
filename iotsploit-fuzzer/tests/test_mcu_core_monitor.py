"""CPU monitoring must never turn an uncertain transport result into a pass."""
import pytest

from iotsploit_fuzzer.harnesses.base import HarnessResult
from iotsploit_fuzzer.harnesses.monitor_set_harness import MonitorSetHarness
from iotsploit_fuzzer.monitors import McuCoreMonitor

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


def harness_for(inner, observe, **kwargs):
    return MonitorSetHarness(inner, [McuCoreMonitor("mcu_core:main", observe, settle_ms=0, **kwargs)])


@pytest.mark.parametrize("state", ["running", "sleeping"])
def test_clean_core_preserves_protocol_timeout(state):
    inner = UARTHarness(HarnessResult(ok=True, timeout=True, response=None))
    harness = harness_for(inner, lambda: observation(state))

    result = harness.execute(b"\x22\xf1\x90")

    assert result.timeout and not result.crashed
    assert inner.sent == [b"\x22\xf1\x90"]
    verdict = result.monitor_verdicts[0]
    assert verdict["verdict"] == "ok"
    assert verdict["before"]["detail"]["state"] == state


@pytest.mark.parametrize("confirmation, crashed", [(observation("fault", 3), True), (observation(), False)])
def test_fault_needs_persistent_exception_evidence(confirmation, crashed):
    samples = iter([observation(), observation("fault", 3), confirmation])
    harness = harness_for(UARTHarness(HarnessResult(ok=True)), lambda: next(samples))

    result = harness.execute(b"trigger")

    assert result.crashed is crashed
    assert result.stop_reason  # Even uncertain fault evidence stops for inspection.
    verdict = result.monitor_verdicts[0]
    assert verdict["evidence"]["confirmation"] == confirmation
    assert verdict["verdict"] == ("crash" if crashed else "inconclusive")


def test_fault_in_another_exception_is_not_persistent():
    samples = iter([observation(), observation("fault", 3), observation("fault", 4)])
    harness = harness_for(UARTHarness(HarnessResult(ok=True)), lambda: next(samples))

    result = harness.execute(b"trigger")

    assert not result.crashed
    assert result.stop_reason == "fault"


@pytest.mark.parametrize("value", [-1, 1001, "20", None, True])
def test_observation_window_is_bounded(value):
    with pytest.raises(ValueError, match="settle_ms"):
        McuCoreMonitor("mcu_core:main", lambda: observation(), value)


def test_confirmed_fault_is_snapshotted_then_recovered_for_next_case():
    samples = iter([observation(), observation("fault", 3), observation("fault", 3),
                    observation(), observation()])
    calls = []
    inner = UARTHarness(HarnessResult(ok=True))
    harness = harness_for(
        inner,
        lambda: next(samples),
        snapshot=lambda: calls.append("snapshot") or {"stack": {"pc": 0x1234}},
        recover=lambda expected: calls.append(("recover", expected)) or {"recovered": True},
        recovery_policy="reset_continue",
    )

    failed = harness.execute(b"fault")
    clean = harness.execute(b"next")

    assert failed.crashed and failed.stop_reason is None
    evidence = failed.monitor_verdicts[0]["evidence"]
    assert evidence["snapshot"]["stack"]["pc"] == 0x1234
    assert evidence["recovery"]["recovered"] is True
    assert failed.monitor_verdicts[0]["detected_reason"].startswith("Persistent fault exception")
    assert calls == ["snapshot", ("recover", False)]
    assert clean.ok and not clean.crashed
    assert inner.sent == [b"fault", b"next"]


def test_snapshot_failure_is_kept_as_evidence():
    samples = iter([observation(), observation("lockup")])

    def broken():
        raise RuntimeError("probe gone")

    harness = harness_for(UARTHarness(HarnessResult(ok=True)), lambda: next(samples), snapshot=broken)

    result = harness.execute(b"x")

    assert result.crashed
    assert result.monitor_verdicts[0]["evidence"]["snapshot"] == {"error": "probe gone"}


def test_expected_reset_waits_for_readiness_without_failing_case():
    samples = iter([observation(), observation("reset")])
    harness = harness_for(
        UARTHarness(HarnessResult(ok=True)),
        lambda: next(samples),
        recover=lambda expected: {"recovered": expected},
        max_recoveries=0,  # expected resets must not consume the failure-recovery budget
        expected_reset_prefixes=(b"\x11\x01",),
    )

    result = harness.execute(b"\x11\x01\x99")

    assert result.ok and not result.crashed and result.stop_reason is None
    verdict = result.monitor_verdicts[0]
    assert verdict["verdict"] == "expected_reset"
    assert verdict["evidence"]["expected_reset"] is True
    assert verdict["evidence"]["recovery"]["recovered"] is True
    assert result.info == "Expected reset observed; target ready"


def test_unexpected_reset_stops_without_recovery_under_stop_policy():
    samples = iter([observation(), observation("reset")])
    harness = harness_for(UARTHarness(HarnessResult(ok=True)), lambda: next(samples),
                          recover=lambda expected: pytest.fail("recovered under stop policy"),
                          expected_reset_prefixes=(b"\x11\x01",))

    result = harness.execute(b"\x22")

    assert not result.ok and result.stop_reason == "reset"


def test_recovery_limit_stops_campaign():
    samples = iter([observation(), observation("lockup")])
    harness = harness_for(
        UARTHarness(HarnessResult(ok=True)),
        lambda: next(samples),
        recover=lambda expected: {"recovered": True},
        recovery_policy="reset_continue",
        max_recoveries=0,
    )

    result = harness.execute(b"fault")

    assert result.stop_reason == "Recovery limit of 0 reached"
    assert result.monitor_verdicts[0]["evidence"]["recovery"]["recovered"] is False


def test_failed_recovery_reports_its_error():
    samples = iter([observation(), observation("lockup")])
    harness = harness_for(
        UARTHarness(HarnessResult(ok=True)),
        lambda: next(samples),
        recover=lambda expected: {"recovered": False, "error": "no boot"},
        recovery_policy="reset_continue",
    )

    assert harness.execute(b"fault").stop_reason == "no boot"


def test_preflight_consumes_one_stale_reset():
    samples = iter([observation("reset"), observation()])
    monitor = McuCoreMonitor("mcu_core:main", lambda: next(samples), settle_ms=0)

    verdict = monitor.preflight()

    assert verdict.verdict == "ok" and verdict.stop_reason is None


def test_preflight_reports_a_second_reset():
    samples = iter([observation("reset"), observation("reset")])
    monitor = McuCoreMonitor("mcu_core:main", lambda: next(samples), settle_ms=0)

    assert monitor.preflight().stop_reason == "reset"
