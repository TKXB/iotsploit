"""Score observed CAN identities against the buses a target documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Tuple

from iotsploit_protocols.canbus.catalog import TargetCanCatalog

Identity = Tuple[int, bool]


def observe_identities(channel: str, seconds: float, *, fd: bool = True) -> set[Identity]:
    """Listen read-only and return distinct data-frame identities."""
    from iotsploit_protocols.canbus.errorframes import is_error_frame, is_remote_frame
    from iotsploit_protocols.canbus.socketcan import (
        CaptureBudget,
        SocketCanConfig,
        SocketCanReceiver,
    )

    seen: set[Identity] = set()
    with SocketCanReceiver(SocketCanConfig(channel=channel, fd=fd)) as receiver:
        for message in receiver.frames(
            CaptureBudget(duration_s=seconds, max_frames=200_000)
        ):
            if is_error_frame(message) or is_remote_frame(message):
                continue
            seen.add((int(message.arbitration_id), bool(message.is_extended_id)))
    return seen


@dataclass(frozen=True)
class BusMatchRow:
    bus_id: str
    bus_name: str
    matched: int
    heard: int
    documented: int

    @property
    def coverage(self) -> float:
        return self.matched / self.heard if self.heard else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "bus_id": self.bus_id,
            "bus_name": self.bus_name,
            "matched": self.matched,
            "heard": self.heard,
            "documented": self.documented,
            "coverage": self.coverage,
        }


@dataclass(frozen=True)
class BusMatchResult:
    outcome: str
    rows: tuple[BusMatchRow, ...]
    best_bus_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        messages = {
            "winner": "One documented bus clearly explains the observed traffic.",
            "none": "No bus explains this traffic. Check the target definitions and interface.",
            "tie": "Two or more buses explain nearly the same traffic. Listen longer.",
            "no_frames": "No data-frame identities were heard during the sample.",
            "no_buses": "The target documents no CAN frames.",
        }
        return {
            "outcome": self.outcome,
            "best_bus_id": self.best_bus_id,
            "message": messages[self.outcome],
            "rows": [row.as_dict() for row in self.rows],
        }


def score_buses(
    catalog: TargetCanCatalog,
    observed: Iterable[Identity],
    *,
    near_tie_ratio: float = 0.9,
) -> BusMatchResult:
    """Return a winner, no-match, or near-tie without guessing.

    Coverage is the portion of observed identities a bus documents. A runner-up
    reaching 90% of the winner is deliberately ambiguous: a longer sample is
    safer than selecting a bus whose definitions happen to overlap heavily.
    """
    if not 0 < near_tie_ratio <= 1:
        raise ValueError("near_tie_ratio must be greater than 0 and at most 1")

    seen = {(int(frame_id), bool(is_extended)) for frame_id, is_extended in observed}
    if not seen:
        return BusMatchResult("no_frames", ())

    rows = []
    for bus in catalog.buses:
        documented = {(frame.frame_id, frame.is_extended) for frame in bus.frames}
        if documented:
            rows.append(
                BusMatchRow(
                    bus_id=bus.bus_id,
                    bus_name=bus.name,
                    matched=len(seen & documented),
                    heard=len(seen),
                    documented=len(documented),
                )
            )
    rows.sort(key=lambda row: (-row.matched, row.bus_id))
    ranked = tuple(rows)
    if not ranked:
        return BusMatchResult("no_buses", ranked)
    if ranked[0].matched == 0:
        return BusMatchResult("none", ranked)

    if len(ranked) > 1:
        runner_up = ranked[1].matched
        if runner_up and runner_up / ranked[0].matched >= near_tie_ratio:
            return BusMatchResult("tie", ranked)
    return BusMatchResult("winner", ranked, best_bus_id=ranked[0].bus_id)
