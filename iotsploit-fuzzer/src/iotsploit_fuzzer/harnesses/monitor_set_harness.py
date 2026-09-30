"""Run a protocol harness while any number of target monitors watch the device."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Optional, Sequence

from ..monitoring.target_monitor import SEVERITY, MonitorVerdict, TargetMonitor
from .base import HarnessResult, ProtocolHarness


class MonitorSetHarness(ProtocolHarness):
    """Every case: all ``before`` checks, the payload, settle, all ``after`` checks.

    No payload is sent while any monitor says the target is unfit. After the
    payload the worst decisive verdict decides the case; corroborating verdicts
    are recorded but never fail or stop anything.
    """

    def __init__(self, inner: ProtocolHarness, monitors: Sequence[TargetMonitor]):
        if not monitors:
            raise ValueError("MonitorSetHarness needs at least one monitor")
        names = [monitor.name for monitor in monitors]
        if len(set(names)) != len(names):
            raise ValueError("Monitor names must be unique")
        self.inner = inner
        self.monitors = list(monitors)
        self.settle_ms = max(monitor.settle_ms for monitor in self.monitors)

    def preflight(self) -> list[MonitorVerdict]:
        return [monitor.preflight() for monitor in self.monitors]

    def execute(self, payload: bytes) -> HarnessResult:
        befores = [monitor.before() for monitor in self.monitors]
        blocked = next((verdict for verdict in befores if verdict.decisive and verdict.stop_reason), None)
        if blocked is not None:
            reason = self._label(blocked, blocked.stop_reason)
            return HarnessResult(ok=False, sent=False, error=reason, stop_reason=reason,
                                 monitor_verdicts=[verdict.to_dict() for verdict in befores])

        result = self.inner.execute(payload)
        time.sleep(self.settle_ms / 1000)
        afters = [monitor.after(payload) for monitor in self.monitors]
        for before, after in zip(befores, afters):
            after.before = before.observation

        decisive = [verdict for verdict in afters if verdict.decisive]
        crashed = any(verdict.verdict == "crash" for verdict in decisive)
        reported = [self._label(verdict, verdict.detected_reason) for verdict in self._ranked(decisive)
                    if verdict.detected_reason and verdict.verdict != "expected_reset"]
        stops = [self._label(verdict, verdict.stop_reason) for verdict in self._ranked(decisive)
                 if verdict.stop_reason]
        notes = [
            "Expected reset observed; target ready" if verdict.verdict == "expected_reset"
            else self._label(verdict, verdict.detected_reason)
            for verdict in afters if verdict.detected_reason
        ]
        return replace(
            result,
            ok=result.ok and not reported,
            crashed=result.crashed or crashed,
            error=result.error or (reported[0] if reported else None),
            stop_reason=stops[0] if stops else None,
            monitor_verdicts=[verdict.to_dict() for verdict in afters],
            info="; ".join(filter(None, (result.info, *notes))) or result.info,
        )

    @staticmethod
    def _ranked(verdicts: list[MonitorVerdict]) -> list[MonitorVerdict]:
        return sorted(verdicts, key=lambda verdict: -SEVERITY[verdict.verdict])

    def _label(self, verdict: MonitorVerdict, text: Optional[str]) -> Optional[str]:
        if text is None or len(self.monitors) == 1:
            return text
        return f"{verdict.monitor}: {text}"
