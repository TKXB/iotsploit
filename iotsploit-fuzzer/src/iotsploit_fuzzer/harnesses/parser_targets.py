"""The parse surfaces this fuzzer points at, and how a payload becomes a call.

A registry entry is data: the callable to reach, the exceptions its own
docstring declares, and the budget one parse gets. Adding a tenth target is an
entry, not code.

Adapters are the only code here, and each is a translation: a fuzzer produces
bytes, while ``scan_log`` wants a path and ``from_target`` wants a mapping.
An adapter that cannot build an input out of a payload raises :class:`Skip`,
which is not a result and is never recorded -- otherwise "this payload was not
valid JSON" would fill the corpus.

Every adapter is resolved *inside the worker subprocess*, by dotted path, so
nothing here has to be picklable and a target that dies takes only the worker
with it.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Tuple


class Skip(Exception):
    """This payload does not form an input for this target."""


class MetamorphicError(Exception):
    """A relation between two calls broke, without either call raising.

    The only class of defect that a crash-only oracle cannot see, and the one
    that matters most on a live bus: a silently wrong value.
    """


@dataclass(frozen=True)
class ParseTarget:
    """One parse surface, with the budget and the contract it is held to."""

    name: str
    #: ``module:function`` taking ``bytes`` and returning the parsed value.
    adapter: str
    #: ``module:ExceptionName`` for every exception the contract declares.
    #: An empty tuple means the contract is "never raises".
    declared: Tuple[str, ...] = ()
    seeds: Tuple[bytes, ...] = ()
    budget_seconds: float = 5.0
    memory_mb: int = 768
    output_kb: int = 256
    payload_max_bytes: int = 1 << 20
    #: Bumped by hand when an adapter's translation changes. Part of the
    #: fingerprint, so bumping it forces a ledger re-baseline rather than
    #: reporting every entry as a boundary movement.
    adapter_version: str = "1"

    @property
    def fingerprint(self) -> str:
        """Identity of the oracle, not of the target.

        A ledger recorded under one fingerprint cannot be diffed against a
        campaign run under another: changing the declared set moves the
        accept/reject line by definition, and every entry would read as a
        boundary movement that nobody caused.
        """
        from ..analysis.outcome import OUTCOME_VERSION

        material = "\x00".join(
            (self.adapter, self.adapter_version, str(OUTCOME_VERSION), *sorted(self.declared))
        )
        return hashlib.sha256(material.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Adapters
# --------------------------------------------------------------------------


def _temp_file(payload: bytes, suffix: str) -> str:
    handle, path = tempfile.mkstemp(suffix=suffix, prefix="fuzz_")
    with os.fdopen(handle, "wb") as fh:
        fh.write(payload)
    return path


def _json_input(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Skip(str(error)) from None
    except RecursionError as error:
        # A payload nested past the interpreter's limit is not an input for
        # the target -- the stack ran out inside ``json``, before any code
        # under test was reached. Reporting it as a violation would blame the
        # decoder for the adapter's own translation step.
        raise Skip(str(error)) from None


def scan_log(payload: bytes) -> Any:
    """`canbus.logfile.scan_log`: any file contents, only CanLogError escapes."""
    from iotsploit_protocols.canbus.logfile import scan_log as target

    path = _temp_file(payload, ".asc")
    try:
        return target(path)
    finally:
        os.unlink(path)


def catalog_from_target(payload: bytes) -> Any:
    """`canbus.catalog.TargetCanCatalog.from_target`: only CanDefinitionError."""
    from iotsploit_protocols.canbus.catalog import TargetCanCatalog

    return TargetCanCatalog.from_target(_json_input(payload))


def _frame_definition(raw: Any) -> Any:
    from iotsploit_protocols.canbus.definitions import (
        FrameDefinition,
        SignalDefinition,
    )

    if not isinstance(raw, dict):
        raise Skip("frame definition must be an object")
    signals = raw.get("signals") or []
    if not isinstance(signals, list):
        raise Skip("signals must be a list")
    try:
        built = tuple(
            SignalDefinition(**s) for s in signals if isinstance(s, dict)
        )
        fields = {k: v for k, v in raw.items() if k != "signals"}
        return FrameDefinition(signals=built, **fields)
    except TypeError as error:
        # An unknown or missing dataclass field is a malformed input, not a
        # defect in the decoder under test.
        raise Skip(str(error)) from None


def decode_frame(payload: bytes) -> Any:
    """`canbus.codec.decode_frame`: never raises, for any definition and bytes."""
    from iotsploit_protocols.canbus.codec import decode_frame as target

    raw = _json_input(payload)
    if not isinstance(raw, dict):
        raise Skip("expected an object")
    try:
        data = bytes.fromhex(str(raw.get("data", "")))
    except ValueError as error:
        raise Skip(str(error)) from None
    return target(_frame_definition(raw.get("definition")), data)


def codec_roundtrip(payload: bytes) -> Any:
    """`decode(encode(v)) == v` -- the only oracle that catches a wrong value."""
    from iotsploit_protocols.canbus.codec import decode_frame, encode_frame

    raw = _json_input(payload)
    if not isinstance(raw, dict):
        raise Skip("expected an object")
    values = raw.get("values")
    if not isinstance(values, dict):
        raise Skip("values must be an object")
    definition = _frame_definition(raw.get("definition"))

    encoded = encode_frame(definition, values)
    decoded = decode_frame(definition, bytes(encoded.data))
    if not decoded.ok:
        raise MetamorphicError(f"encode succeeded but decode failed: {decoded.reason}")

    by_name = {signal.name: signal for signal in definition.signals}
    for name, sent in values.items():
        got = decoded.signals.get(name)
        if not isinstance(sent, (int, float)) or not isinstance(got, (int, float)):
            continue
        if not _raw_representable(by_name.get(name), sent):
            # ``physical = raw * factor + offset``, so a value between two raw
            # steps cannot survive the trip and its loss is quantisation, not
            # a defect. Asserting equality for those would report the codec
            # working as designed.
            continue
        if abs(float(got) - float(sent)) > 1e-6:
            raise MetamorphicError(f"signal {name} survived encode as {got}")
    return decoded


def _raw_representable(signal: Any, value: float) -> bool:
    """Whether the raw encoding can hold this value exactly."""
    if signal is None:
        return False
    try:
        steps = (float(value) - float(signal.offset)) / float(signal.factor)
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    return abs(steps - round(steps)) < 1e-9


def uds_parse(payload: bytes) -> Any:
    """`doip.uds.UdsClient._parse`: any response bytes, only ProtocolError."""
    from iotsploit_protocols.doip.uds import UdsClient

    if not payload:
        raise Skip("empty payload carries no service byte")
    return UdsClient._parse(payload[0], payload[1:])


def sd_parse(payload: bytes) -> Any:
    """`someip.sd.ServiceDiscovery._parse`: any datagram, always a list."""
    from iotsploit_protocols.someip.sd import ServiceDiscovery

    return ServiceDiscovery._parse(payload, "203.0.113.5")


def normalize_request(payload: bytes) -> Any:
    """`frame_composer.normalize_request`: any JSON, only RequestError."""
    from iotsploit_exploits.canbus.frame_composer import normalize_request as target

    try:
        return target(payload.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise Skip(str(error)) from None


def arxml_inspect(payload: bytes) -> Any:
    """`autosar.arxml._inspect_file`: a DTD is refused in every encoding."""
    from iotsploit_protocols.autosar.arxml import _inspect_file
    from pathlib import Path

    path = _temp_file(payload, ".arxml")
    try:
        return _inspect_file(Path(path))
    finally:
        os.unlink(path)


def parse_target_bits(payload: bytes) -> Any:
    """`core.bit_manipulator.parse_target_bits`: operator input, only ValueError.

    The fuzzer's own operator-facing parser. It belongs in the registry for the
    same reason every other entry does, and it is where the MemoryError that
    motivated the worker isolation was found.
    """
    from ..core.bit_manipulator import parse_target_bits as target

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Skip(str(error)) from None
    return target(text)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

_HERE = "iotsploit_fuzzer.harnesses.parser_targets"

_ASC_SEED = (
    b"date Mon Jan 1 00:00:00 2024\n"
    b"base hex timestamps absolute\n"
    b"Begin Triggerblock Mon Jan 1 00:00:00 2024\n"
    b"   0.000100 1  123             Rx   d 8 11 22 33 44 55 66 77 88\n"
    b"   0.000200 1  1FFFFFFFx       Rx   d 2 AA BB\n"
    b"End TriggerBlock\n"
)

_FRAME_SEED = {
    "bus_id": "bus-1",
    "frame_id": 291,
    "is_extended": False,
    "name": "EngineStatus",
    "dlc": 8,
    "signals": [
        {"name": "Speed", "start_bit": 0, "length": 16, "factor": 0.1},
        {"name": "Gear", "start_bit": 16, "length": 4},
    ],
}

_TARGET_SEED = {
    "buses": [{"id": "bus-1", "name": "PT", "protocol": "CAN", "frames": [_FRAME_SEED]}],
    "components": [],
}


def _json_seed(obj: Any) -> bytes:
    return json.dumps(obj).encode()


REGISTRY: Dict[str, ParseTarget] = {}


def register(target: ParseTarget) -> ParseTarget:
    """Add a target to the registry, replacing any entry of the same name."""
    REGISTRY[target.name] = target
    return target


for _target in (
    ParseTarget(
        name="canbus.scan_log",
        adapter=f"{_HERE}:scan_log",
        declared=("iotsploit_protocols.canbus.logfile:CanLogError",),
        seeds=(_ASC_SEED, b"", b"garbage\n"),
        budget_seconds=5.0,
    ),
    ParseTarget(
        name="canbus.from_target",
        adapter=f"{_HERE}:catalog_from_target",
        declared=("iotsploit_protocols.canbus.errors:CanDefinitionError",),
        seeds=(_json_seed(_TARGET_SEED), b"null", b"{}", b"[]"),
    ),
    ParseTarget(
        name="canbus.decode_frame",
        adapter=f"{_HERE}:decode_frame",
        declared=(),
        seeds=(
            _json_seed({"definition": _FRAME_SEED, "data": "1122334455667788"}),
            _json_seed({"definition": _FRAME_SEED, "data": ""}),
        ),
    ),
    ParseTarget(
        name="canbus.codec_roundtrip",
        adapter=f"{_HERE}:codec_roundtrip",
        declared=(
            "iotsploit_protocols.canbus.errors:CanValueError",
            "iotsploit_protocols.canbus.errors:CanDefinitionError",
        ),
        # 2: the round trip is asserted only where the raw encoding can
        # represent the value. Version 1 reported quantisation as a broken
        # invariant, so its recorded signatures are not comparable.
        adapter_version="2",
        seeds=(
            _json_seed({"definition": _FRAME_SEED, "values": {"Speed": 12.8, "Gear": 3}}),
        ),
    ),
    ParseTarget(
        name="doip.uds_parse",
        adapter=f"{_HERE}:uds_parse",
        declared=("iotsploit_protocols.errors:ProtocolError",),
        seeds=(b"\x22\x62\xf1\x90\x01\x02", b"\x10\x7f\x10\x11", b"\x22", b"\x00"),
    ),
    ParseTarget(
        name="someip.sd_parse",
        adapter=f"{_HERE}:sd_parse",
        declared=(),
        seeds=(bytes.fromhex("ffff810000000020000000010100020000000000"), b"", b"\x00" * 16),
    ),
    ParseTarget(
        name="composer.normalize_request",
        adapter=f"{_HERE}:normalize_request",
        declared=("iotsploit_exploits.canbus.frame_composer:RequestError",),
        seeds=(
            _json_seed(
                {
                    "schema_version": 1,
                    "operation": "preview",
                    "frame": {"bus_id": "bus-1", "frame_id": 291},
                    "signals": {"Speed": 12.8},
                }
            ),
            _json_seed({"schema_version": 1, "frame": {"bus_id": "b", "frame_id": "0x123"}}),
            b"{}",
            b"",
        ),
    ),
    ParseTarget(
        name="autosar.inspect_file",
        adapter=f"{_HERE}:arxml_inspect",
        declared=("iotsploit_protocols.autosar.arxml:ArxmlImportError",),
        seeds=(
            b"<?xml version=\"1.0\"?><AUTOSAR><AR-PACKAGES/></AUTOSAR>",
            b"<!DOCTYPE a []><a/>",
        ),
    ),
    ParseTarget(
        name="fuzzer.parse_target_bits",
        adapter=f"{_HERE}:parse_target_bits",
        declared=("builtins:ValueError",),
        seeds=(b"0-7", b"0,1,7", b"0-7,16,17", b"5"),
        budget_seconds=2.0,
        memory_mb=512,
    ),
):
    register(_target)

del _target
