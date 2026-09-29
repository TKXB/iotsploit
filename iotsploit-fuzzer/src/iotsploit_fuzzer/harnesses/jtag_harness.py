"""Compose protocol execution with one externally owned debug session."""
import time
from dataclasses import replace
from typing import Callable, Optional

from .base import HarnessResult, ProtocolHarness


class JtagHarness(ProtocolHarness):
    def __init__(
        self,
        inner: ProtocolHarness,
        observe: Callable[[], dict],
        settle_ms: int = 20,
        *,
        snapshot: Optional[Callable[[], dict]] = None,
        recover: Optional[Callable[[bool], dict]] = None,
        recovery_policy: str = "stop",
        max_recoveries: int = 3,
        expected_reset_prefixes: tuple[bytes, ...] = (),
    ):
        if not isinstance(settle_ms, int) or not 0 <= settle_ms <= 1000:
            raise ValueError("settle_ms must be an integer between 0 and 1000")
        if recovery_policy not in ("stop", "reset_continue"):
            raise ValueError("recovery_policy must be stop or reset_continue")
        if not isinstance(max_recoveries, int) or not 0 <= max_recoveries <= 100:
            raise ValueError("max_recoveries must be an integer between 0 and 100")
        self.inner = inner
        self.observe = observe
        self.settle_ms = settle_ms
        self.snapshot = snapshot
        self.recover = recover
        self.recovery_policy = recovery_policy
        self.max_recoveries = max_recoveries
        self.expected_reset_prefixes = expected_reset_prefixes
        self.recoveries = 0
        self.last_observation = None

    def check(self) -> dict:
        observation = self.observe()
        # A single sample in a fault handler does not establish persistent failure.
        if observation["state"] == "fault" and observation.get("active_exception") in (3, 4, 5, 6):
            time.sleep(self.settle_ms / 1000)
            confirmation = self.observe()
            observation["confirmation"] = confirmation
            if confirmation.get("active_exception") == observation["active_exception"] and confirmation["state"] == "fault":
                observation["crashed"] = True
                observation["stop_reason"] = (
                    f"Persistent fault exception observed: "
                    f"{', '.join(observation.get('fault_causes', [])) or 'cause unavailable'}"
                )
        self.last_observation = observation
        return observation

    def _capture_snapshot(self, observation: dict) -> None:
        failed_core = observation.get("crashed") or observation["state"] in ("lockup", "halted")
        if self.snapshot is None or not failed_core:
            return
        try:
            observation["snapshot"] = self.snapshot()
        except Exception as exc:
            observation["snapshot"] = {"error": str(exc)}

    def _recover(self, observation: dict, *, expected_reset: bool) -> bool:
        should_recover = expected_reset or self.recovery_policy == "reset_continue"
        if not should_recover or self.recover is None:
            return False
        # Expected resets are protocol behavior, not failures, so only
        # failure recoveries count against the limit.
        if not expected_reset:
            if self.recoveries >= self.max_recoveries:
                observation["recovery"] = {
                    "recovered": False,
                    "error": f"Recovery limit of {self.max_recoveries} reached",
                }
                observation["stop_reason"] = observation["recovery"]["error"]
                return False
            self.recoveries += 1
        try:
            recovery = self.recover(expected_reset)
        except Exception as exc:
            recovery = {"recovered": False, "error": str(exc)}
        observation["recovery"] = recovery
        if recovery.get("recovered"):
            return True
        observation["stop_reason"] = recovery.get("error") or "Target recovery failed"
        return False

    def execute(self, payload: bytes) -> HarnessResult:
        before = self.check()
        if before["stop_reason"]:
            return HarnessResult(ok=False, sent=False, error=before["stop_reason"],
                                 stop_reason=before["stop_reason"], core_observation=before)
        result = self.inner.execute(payload)
        time.sleep(self.settle_ms / 1000)
        after = self.check()
        after["before"] = before
        reason = after["stop_reason"]
        expected_reset = after["state"] == "reset" and any(
            payload.startswith(prefix) for prefix in self.expected_reset_prefixes
        )
        if expected_reset:
            after["expected_reset"] = True
        self._capture_snapshot(after)
        recovered = bool(reason) and self._recover(after, expected_reset=expected_reset)
        stop_reason = None if recovered else after["stop_reason"]
        if reason:
            after["detected_reason"] = reason
        after["stop_reason"] = stop_reason
        reported_reason = None if expected_reset and recovered else reason
        info = "Expected reset observed; target ready" if expected_reset and recovered else reason
        return replace(result, ok=result.ok and reported_reason is None,
                       crashed=result.crashed or after["crashed"],
                       error=result.error or reported_reason, stop_reason=stop_reason,
                       core_observation=after,
                       info="; ".join(filter(None, (result.info, info))) or result.info)
