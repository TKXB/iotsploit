"""Telling a bus fault apart from a frame, before anything reads an address.

A SocketCAN socket delivers bus faults as *error frames*, and python-can turns
them on by default (``CAN_RAW_ERR_FILTER``). They are not messages. The
``CAN_ERR_FLAG`` lives in the CAN ID, and python-can masks it off before it
exposes ``arbitration_id``, so what is left there is an error *class*, not an
address: ``CAN_ERR_CRTL`` arrives looking exactly like a frame with id ``0x004``
whose ``data[1]`` happens to be the controller status.

Anything that keys on ``(arbitration_id, is_extended)`` without testing
``is_error_frame`` first therefore invents a frame ``0x004`` no ECU ever sent
and counts bus faults as traffic. For a capture that writes observations the
consequence is worse than a wrong number on a screen: it records that phantom
frame as a documented-versus-observed finding against the target.

Why this exists twice
---------------------
``iotsploit_drivers.socketcan.can_errors`` holds the same constants, and the
duplication is deliberate rather than an oversight. ``iotsploit-drivers``
depends on ``iotsploit-core`` alone, and the dependency direction both CAN plans
fix is ``exploits -> protocols -> core``; importing the driver package from here
would add an edge neither plan sanctions, to reach nine integers out of
``linux/can/error.h`` that have not changed since 2007. The precedent is
``canonical_frame_id``, duplicated for the same reason.

The two are not redundant in what they produce. The driver formats a
``candump -e`` style description for a live stream; a capture needs a per-class
tally it can total over a window. They share the vocabulary, not the output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

# Error class, carried in the masked arbitration id. linux/can/error.h.
CAN_ERR_TX_TIMEOUT = 0x001
CAN_ERR_LOSTARB = 0x002
CAN_ERR_CRTL = 0x004
CAN_ERR_PROT = 0x008
CAN_ERR_TRX = 0x010
CAN_ERR_ACK = 0x020
CAN_ERR_BUSOFF = 0x040
CAN_ERR_BUSERROR = 0x080
CAN_ERR_RESTARTED = 0x100

ERROR_CLASSES: Dict[int, str] = {
    CAN_ERR_TX_TIMEOUT: "tx-timeout",
    CAN_ERR_LOSTARB: "lost-arbitration",
    CAN_ERR_CRTL: "controller-problem",
    CAN_ERR_PROT: "protocol-violation",
    CAN_ERR_TRX: "transceiver-status",
    CAN_ERR_ACK: "no-acknowledgement-on-tx",
    CAN_ERR_BUSOFF: "bus-off",
    CAN_ERR_BUSERROR: "bus-error",
    CAN_ERR_RESTARTED: "controller-restarted",
}

#: Controller status, ``data[1]``. These are the ones worth surfacing to an
#: operator: a bus sitting at error-passive is saying the bitrate is wrong, the
#: FD configuration is wrong, or the wiring is wrong -- which is the actual
#: explanation for a capture that "sees nothing".
CONTROLLER_STATUS: Dict[int, str] = {
    0x01: "rx-overflow",
    0x02: "tx-overflow",
    0x04: "rx-error-warning",
    0x08: "tx-error-warning",
    0x10: "rx-error-passive",
    0x20: "tx-error-passive",
    0x40: "back-to-error-active",
}

#: Statuses that mean the link is degraded rather than merely noisy. A capture
#: whose data-frame count is low and whose faults are these must say so instead
#: of reporting an empty bus.
DEGRADED_STATUSES = frozenset(
    {"rx-error-passive", "tx-error-passive", "rx-error-warning", "tx-error-warning"}
)


@dataclass(frozen=True)
class ErrorFrame:
    """One classified fault, reduced to what a tally needs."""

    classes: Tuple[str, ...]
    controller_status: Tuple[str, ...] = ()

    @property
    def labels(self) -> Tuple[str, ...]:
        """Every name this fault should be counted under."""
        return self.classes + self.controller_status

    @property
    def is_degraded(self) -> bool:
        return "bus-off" in self.classes or any(
            status in DEGRADED_STATUSES for status in self.controller_status
        )


def _flag_names(mapping: Mapping[int, str], value: int) -> List[str]:
    return [name for bit, name in sorted(mapping.items()) if value & bit]


def classify_error_frame(arbitration_id: int, data: Any = None) -> ErrorFrame:
    """Read an error frame's class, and the controller status when it has one.

    ``arbitration_id`` is what python-can exposes after masking off
    ``CAN_ERR_FLAG``: a bitmask of error classes, never an address.
    """
    classes = tuple(_flag_names(ERROR_CLASSES, int(arbitration_id or 0)))
    if not classes:
        classes = ("unknown-error-class",)

    status: Tuple[str, ...] = ()
    if int(arbitration_id or 0) & CAN_ERR_CRTL:
        payload = bytes(data or b"")
        if len(payload) > 1:
            status = tuple(_flag_names(CONTROLLER_STATUS, payload[1]))

    return ErrorFrame(classes=classes, controller_status=status)


def is_error_frame(message: Any) -> bool:
    """Whether this is a fault rather than traffic.

    Read before identity, always. A message object that does not carry the
    attribute is treated as traffic, which is the safe default for a scripted
    frame source in a test.
    """
    return bool(getattr(message, "is_error_frame", False))


def is_remote_frame(message: Any) -> bool:
    """Whether this is a remote request rather than a data frame.

    Its own category: a remote frame carries no payload, and counting it as a
    zero-length data frame would report a frame whose signals are all zero.
    """
    return bool(getattr(message, "is_remote_frame", False))
