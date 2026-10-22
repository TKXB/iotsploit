"""Classification of SocketCAN error frames.

A SocketCAN socket delivers bus faults as *error frames*, and python-can turns
them on by default (``CAN_RAW_ERR_FILTER``). They are not messages. The
``CAN_ERR_FLAG`` lives in the CAN ID, and python-can masks it off before it
exposes ``arbitration_id``, so what is left there is an error *class* -- not an
address. ``CAN_ERR_CRTL`` arrives looking exactly like a frame with id ``0x004``
whose ``data[1]`` happens to be the controller status.

Anything that reads ``arbitration_id`` without checking ``is_error_frame``
first therefore invents a frame ``0x004`` that no ECU ever sent, and reports a
faulted bus as traffic. That is the bug this module exists to prevent.

The field meanings are ``linux/can/error.h``. ``description`` is formatted the
way ``candump -e`` prints it, so an operator can match the two by eye.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

# Error class, carried in the masked arbitration id.
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

#: Controller status, data[1]. Names match what ``candump -e`` prints, so the
#: two can be compared line by line; ``back-to-error-active`` is the one piece
#: of good news in here, meaning the counters came back down.
CONTROLLER_STATUS: Dict[int, str] = {
    0x01: "rx-overflow",
    0x02: "tx-overflow",
    0x04: "rx-error-warning",
    0x08: "tx-error-warning",
    0x10: "rx-error-passive",
    0x20: "tx-error-passive",
    0x40: "back-to-error-active",
}

#: Protocol violation type, data[2].
PROTOCOL_TYPE: Dict[int, str] = {
    0x01: "bit",
    0x02: "form",
    0x04: "stuff",
    0x08: "bit0",
    0x10: "bit1",
    0x20: "overload",
    0x40: "active-announcement",
    0x80: "on-transmission",
}

#: Protocol violation location, data[3]. Not a bit field: one value.
PROTOCOL_LOCATION: Dict[int, str] = {
    0x00: "unspecified",
    0x02: "id28-21",
    0x03: "start-of-frame",
    0x04: "substitute-rtr",
    0x05: "identifier-extension",
    0x06: "id20-18",
    0x07: "id17-13",
    0x08: "crc-sequence",
    0x09: "reserved-bit-0",
    0x0A: "data-section",
    0x0B: "data-length-code",
    0x0C: "rtr",
    0x0D: "reserved-bit-1",
    0x0E: "id04-00",
    0x0F: "id12-05",
    0x12: "intermission",
    0x18: "crc-delimiter",
    0x19: "ack-slot",
    0x1A: "end-of-frame",
    0x1B: "ack-delimiter",
}

#: Transceiver status, data[4]. Not a bit field: one value.
TRANSCEIVER_STATUS: Dict[int, str] = {
    0x00: "unspecified",
    0x04: "canh-no-wire",
    0x05: "canh-short-to-bat",
    0x06: "canh-short-to-vcc",
    0x07: "canh-short-to-gnd",
    0x40: "canl-no-wire",
    0x50: "canl-short-to-bat",
    0x60: "canl-short-to-vcc",
    0x70: "canl-short-to-gnd",
    0x80: "canl-short-to-canh",
}

_KNOWN_CLASS_MASK = 0
for _bit in ERROR_CLASSES:
    _KNOWN_CLASS_MASK |= _bit


def _flag_names(mapping: Mapping[int, str], value: int) -> List[str]:
    """Every name whose bit is set, or ``unspecified`` for a zero byte."""
    if value == 0:
        return ["unspecified"]
    names = [name for bit, name in sorted(mapping.items()) if value & bit]
    unknown = value & ~sum(mapping)
    if unknown:
        names.append(f"unknown(0x{unknown:02X})")
    return names


def _byte(data: bytes, index: int) -> Optional[int]:
    """``data[index]`` when the frame is long enough, else None.

    An error frame is supposed to carry 8 bytes, but a short one must not
    become an IndexError inside an acquisition loop.
    """
    return data[index] if len(data) > index else None


def decode_error_frame(arbitration_id: int, data: Optional[Iterable[int]] = None) -> Dict[str, Any]:
    """Describe one error frame.

    ``arbitration_id`` is the value python-can reports, with ``CAN_ERR_FLAG``
    already masked off, so it holds only error class bits. ``data`` is the
    frame payload, whose meaning depends on which classes are set.
    """
    payload = bytes(data or b"")
    classes = [name for bit, name in sorted(ERROR_CLASSES.items()) if arbitration_id & bit]

    unknown_bits = arbitration_id & ~_KNOWN_CLASS_MASK
    if unknown_bits:
        classes.append(f"unknown(0x{unknown_bits:03X})")
    if not classes:
        classes = ["unspecified"]

    detail: Dict[str, Any] = {}

    if arbitration_id & CAN_ERR_LOSTARB:
        bit_number = _byte(payload, 0)
        if bit_number is not None:
            # 0 means "the controller did not say which bit".
            detail["lost_arbitration_bit"] = bit_number or None

    if arbitration_id & CAN_ERR_CRTL:
        status = _byte(payload, 1)
        if status is not None:
            detail["controller"] = _flag_names(CONTROLLER_STATUS, status)

    if arbitration_id & CAN_ERR_PROT:
        kind = _byte(payload, 2)
        if kind is not None:
            detail["protocol"] = _flag_names(PROTOCOL_TYPE, kind)
        location = _byte(payload, 3)
        if location is not None:
            detail["protocol_location"] = PROTOCOL_LOCATION.get(location, f"unknown(0x{location:02X})")

    if arbitration_id & CAN_ERR_TRX:
        status = _byte(payload, 4)
        if status is not None:
            detail["transceiver"] = TRANSCEIVER_STATUS.get(status, f"unknown(0x{status:02X})")

    return {
        "classes": classes,
        "description": _describe(classes, detail),
        "error_class_id": arbitration_id,
        "data": payload.hex(),
        **detail,
    }


def _describe(classes: List[str], detail: Mapping[str, Any]) -> str:
    """``controller-problem{rx-warning}``, the shape ``candump -e`` prints."""
    parts = []
    for name in classes:
        if name == "controller-problem" and "controller" in detail:
            parts.append(f"{name}{{{','.join(detail['controller'])}}}")
        elif name == "protocol-violation" and "protocol" in detail:
            location = detail.get("protocol_location")
            inner = ",".join(detail["protocol"])
            parts.append(f"{name}{{{inner}}}" + (f"@{location}" if location else ""))
        elif name == "transceiver-status" and "transceiver" in detail:
            parts.append(f"{name}{{{detail['transceiver']}}}")
        else:
            parts.append(name)
    return " ".join(parts)
