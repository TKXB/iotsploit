"""Policy for ``mcu_core`` monitors: is the CPU still running the firmware?"""

from __future__ import annotations

import time
from typing import Callable, Optional

from ..monitoring.target_monitor import MonitorVerdict

KIND = "mcu_core"


class McuCoreMonitor:
    """Judge one CPU core before and after every payload.

    ``observe`` returns one ``mcu_core`` observation (a dict with a ``detail``);
    ``snapshot`` captures a failed core's context; ``recover`` restarts it and
    reports ``{"recovered": bool, ...}``. All three come from the monitor source.
    """

    def __init__(
        self,
        name: str,
        observe: Callable[[], dict],
        settle_ms: int = 20,
        *,
        snapshot: Optional[Callable[[], dict]] = None,
        recover: Optional[Callable[[bool], dict]] = None,
        recovery_policy: str = "stop",
        max_recoveries: int = 3,
        expected_reset_prefixes: tuple[bytes, ...] = (),
    ):
        if not isinstance(settle_ms, int) or isinstance(settle_ms, bool) or not 0 <= settle_ms <= 1000:
            raise ValueError("settle_ms must be an integer between 0 and 1000")
        if recovery_policy not in ("stop", "reset_continue"):
            raise ValueError("recovery_policy must be stop or reset_continue")
        if not isinstance(max_recoveries, int) or not 0 <= max_recoveries <= 100:
            raise ValueError("max_recoveries must be an integer between 0 and 100")
        self.name = name
        self.kind = KIND
        self.observe = observe
        self.settle_ms = settle_ms
        self.snapshot = snapshot
        self.recover = recover
        self.recovery_policy = recovery_policy
        self.max_recoveries = max_recoveries
        self.expected_reset_prefixes = expected_reset_prefixes
        self.recoveries = 0

    def preflight(self) -> MonitorVerdict:
        verdict = self.before()
        # The first reset indication describes time before this campaign.
        # Consume it here, before any case, and require a usable second sample.
        if _state(verdict.observation) == "reset":
            verdict = self.before()
        return verdict

    def before(self) -> MonitorVerdict:
        observation, crashed, reason, evidence = self._check()
        return self._verdict(observation, crashed, reason, stop_reason=reason, evidence=evidence)

    def after(self, payload: bytes) -> MonitorVerdict:
        observation, crashed, reason, evidence = self._check()
        state = _state(observation)
        expected_reset = state == "reset" and any(
            payload.startswith(prefix) for prefix in self.expected_reset_prefixes
        )
        if expected_reset:
            evidence["expected_reset"] = True
        if self.snapshot is not None and (crashed or state in ("lockup", "halted")):
            try:
                evidence["snapshot"] = self.snapshot()
            except Exception as exc:
                evidence["snapshot"] = {"error": str(exc)}
        stop_reason = reason
        recovered = False
        if reason:
            recovered, failure = self._recover(evidence, expected_reset=expected_reset)
            stop_reason = None if recovered else (failure or reason)
        verdict = self._verdict(observation, crashed, reason, stop_reason=stop_reason, evidence=evidence)
        if expected_reset and recovered:
            verdict.verdict = "expected_reset"
        return verdict

    def _check(self) -> tuple[dict, bool, Optional[str], dict]:
        observation = self.observe()
        detail = observation["detail"]
        crashed = detail["state"] == "lockup"
        reason = detail.get("cause")
        evidence: dict = {}
        # A single sample in a fault handler does not establish persistent failure.
        if detail["state"] == "fault":
            time.sleep(self.settle_ms / 1000)
            confirmation = self.observe()
            evidence["confirmation"] = confirmation
            again = confirmation["detail"]
            if again["state"] == "fault" and again.get("active_exception") == detail.get("active_exception"):
                crashed = True
                reason = (
                    "Persistent fault exception observed: "
                    f"{', '.join(detail.get('fault_causes') or []) or 'cause unavailable'}"
                )
        return observation, crashed, reason, evidence

    def _recover(self, evidence: dict, *, expected_reset: bool) -> tuple[bool, Optional[str]]:
        if not (expected_reset or self.recovery_policy == "reset_continue") or self.recover is None:
            return False, None
        # Expected resets are protocol behaviour, not failures, so only failure
        # recoveries count against the limit.
        if not expected_reset:
            if self.recoveries >= self.max_recoveries:
                error = f"Recovery limit of {self.max_recoveries} reached"
                evidence["recovery"] = {"recovered": False, "error": error}
                return False, error
            self.recoveries += 1
        try:
            recovery = self.recover(expected_reset)
        except Exception as exc:
            recovery = {"recovered": False, "error": str(exc)}
        evidence["recovery"] = recovery
        if recovery.get("recovered"):
            return True, None
        return False, recovery.get("error") or "Target recovery failed"

    def _verdict(self, observation: dict, crashed: bool, reason: Optional[str], *,
                 stop_reason: Optional[str], evidence: dict) -> MonitorVerdict:
        if crashed:
            verdict = "crash"
        elif reason:
            verdict = "inconclusive"
        else:
            verdict = "ok"
        return MonitorVerdict(
            monitor=self.name, kind=self.kind, verdict=verdict, observation=observation,
            stop_reason=stop_reason, detected_reason=reason, evidence=evidence,
        )


def _state(observation: dict) -> Optional[str]:
    return observation.get("detail", {}).get("state")
