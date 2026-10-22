"""The default policy: judge any kind by the health its source reports."""

from __future__ import annotations

from typing import Callable

from ..monitoring.target_monitor import MonitorVerdict

# A degraded target is reported but kept under test; anything else not ok stops.
_VERDICTS = {"ok": "ok", "degraded": "inconclusive", "fault": "crash"}


class HealthMonitor:
    """For kinds that bring no policy of their own.

    ``observe`` returns one observation envelope; its ``health`` decides:
    ``ok`` passes, ``degraded`` is reported without stopping, ``fault`` is a
    crash, and ``reset``, ``unavailable`` or anything else stops the campaign.
    """

    def __init__(self, name: str, kind: str, observe: Callable[[], dict], settle_ms: int = 0):
        self.name = name
        self.kind = kind
        self.observe = observe
        self.settle_ms = settle_ms

    def preflight(self) -> MonitorVerdict:
        return self.before()

    def before(self) -> MonitorVerdict:
        return self._verdict(self.observe())

    def after(self, payload: bytes) -> MonitorVerdict:
        return self._verdict(self.observe())

    def _verdict(self, observation: dict) -> MonitorVerdict:
        health = observation.get("health")
        verdict = _VERDICTS.get(health, "inconclusive")
        reason = None
        if verdict != "ok":
            reason = "; ".join(observation.get("reasons") or []) or f"{self.kind} health is {health}"
        return MonitorVerdict(
            monitor=self.name, kind=self.kind, verdict=verdict, observation=observation,
            stop_reason=None if health == "degraded" else reason, detected_reason=reason,
        )
