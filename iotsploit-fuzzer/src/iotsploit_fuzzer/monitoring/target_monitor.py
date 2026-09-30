"""Target monitors: judging what the device under test did during a test case.

A target monitor wraps one monitor source -- a CPU core over SWD today, a UART
console or a supply rail later -- and decides what each observation means for
the payload that preceded it. It never touches hardware itself: the campaign
runtime hands it the source's methods as plain callables, and it reads the
source's observation as a plain dict. This package therefore needs nothing from
``iotsploit_core``.

Not to be confused with ``BaseMonitor`` (which counts harness results) or
``BoundaryMonitor`` (which tracks parser outcomes). Neither watches the target.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Protocol

#: Ascending severity. The harness reports the worst verdict of a case.
VERDICTS = ("ok", "expected_reset", "inconclusive", "hang", "crash")
SEVERITY = {verdict: rank for rank, verdict in enumerate(VERDICTS)}


@dataclass
class MonitorVerdict:
    monitor: str
    kind: str
    verdict: str
    """One of :data:`VERDICTS`. ``inconclusive``: evidence worth stopping for, not a crash."""
    observation: dict
    stop_reason: Optional[str] = None
    """Set when the campaign must stop; None once a recovery made the target usable."""
    detected_reason: Optional[str] = None
    """What the monitor saw, kept even after a successful recovery."""
    decisive: bool = True
    """False for corroborating evidence, which is reported but never stops or fails a case."""
    before: Optional[dict] = None
    evidence: dict = field(default_factory=dict)
    """Kind-specific extras: confirmation samples, fault snapshots, recovery results."""

    def __post_init__(self):
        if self.verdict not in SEVERITY:
            raise ValueError(f"Unknown monitor verdict {self.verdict!r}")

    def to_dict(self) -> dict:
        return asdict(self)


class TargetMonitor(Protocol):
    name: str
    kind: str
    settle_ms: int
    """How long after a payload this monitor needs before ``after`` means anything."""

    def preflight(self) -> MonitorVerdict:
        """Establish a baseline before the first case; may discard stale state."""
        ...

    def before(self) -> MonitorVerdict:
        """Check the target is fit to receive the next payload."""
        ...

    def after(self, payload: bytes) -> MonitorVerdict:
        """Judge the target after ``payload``, recovering it if policy allows."""
        ...
