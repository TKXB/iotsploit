"""Compose protocol execution with one externally owned debug session."""
import time
from dataclasses import replace
from typing import Callable

from .base import HarnessResult, ProtocolHarness


class JtagHarness(ProtocolHarness):
    def __init__(self, inner: ProtocolHarness, observe: Callable[[], dict], settle_ms: int = 20):
        if not isinstance(settle_ms, int) or not 0 <= settle_ms <= 1000:
            raise ValueError("settle_ms must be an integer between 0 and 1000")
        self.inner = inner
        self.observe = observe
        self.settle_ms = settle_ms
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
                observation["stop_reason"] = "Persistent fault exception observed"
        self.last_observation = observation
        return observation

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
        return replace(result, ok=result.ok and reason is None,
                       crashed=result.crashed or after["crashed"],
                       error=result.error or reason, stop_reason=reason,
                       core_observation=after,
                       info="; ".join(filter(None, (result.info, reason))) or result.info)
