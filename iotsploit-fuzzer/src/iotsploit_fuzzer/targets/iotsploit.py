"""IoTSploit's own parse targets: the surfaces, and how a payload becomes a call.

A registry entry is data -- the callable to reach, the exceptions its own
docstring declares, and the budget one parse gets. Adding a target is an entry
and an adapter, not a change to the engine.

This is a *pack*: an ordinary module that calls
:func:`~iotsploit_fuzzer.harnesses.parser_targets.register`. Another
application writes its own and names it with ``--targets``; nothing in the
engine knows about anything below.

The surfaces are grouped by where their input comes from, which is the only
ranking that matters: a file a tester was handed, the output of a tool this
repository does not own, bytes from a vehicle, or a person typing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..harnesses.parser_targets import (
    MetamorphicError,
    ParseTarget,
    Skip,
    json_input,
    json_object,
    register,
    temp_file,
    text_input,
)



def scan_log(payload: bytes) -> Any:
    """`canbus.logfile.scan_log`: any file contents, only CanLogError escapes."""
    from iotsploit_protocols.canbus.logfile import scan_log as target

    path = temp_file(payload, ".asc")
    try:
        return target(path)
    finally:
        os.unlink(path)


def catalog_from_target(payload: bytes) -> Any:
    """`canbus.catalog.TargetCanCatalog.from_target`: only CanDefinitionError."""
    from iotsploit_protocols.canbus.catalog import TargetCanCatalog

    return TargetCanCatalog.from_target(json_input(payload))


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

    raw = json_object(payload, "expected an object")
    try:
        data = bytes.fromhex(str(raw.get("data", "")))
    except ValueError as error:
        raise Skip(str(error)) from None
    return target(_frame_definition(raw.get("definition")), data)


def codec_roundtrip(payload: bytes) -> Any:
    """`decode(encode(v)) == v` -- the only oracle that catches a wrong value."""
    from iotsploit_protocols.canbus.codec import decode_frame, encode_frame

    raw = json_object(payload, "expected an object")
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
    """Whether the raw encoding can hold this value exactly.

    Asked by quantising and rebuilding, not by looking at the fractional part
    of the step count. With a factor of 1e20 every value sits a tiny fraction
    of a step from an integer, so the fractional test called everything
    representable and then reported the codec for losing it -- which is the
    encoding working exactly as ``physical = raw * factor + offset`` says it
    must.
    """
    if signal is None:
        return False
    try:
        offset, factor = float(signal.offset), float(signal.factor)
        steps = (float(value) - offset) / factor
        rebuilt = round(steps) * factor + offset
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return False
    return abs(rebuilt - float(value)) <= 1e-6 * max(1.0, abs(float(value)))


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

    path = temp_file(payload, ".arxml")
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



# -- the rest of the toolkit ------------------------------------------------
#
# The first nine targets came from one plan's survey of the CAN/DoIP/SOME/IP
# parse path. These are the surfaces around it that take input from the same
# three places: a file an operator was handed, the output of a tool this
# repository does not own, and a person typing.


def parse_dbc(payload: bytes) -> Any:
    """`django.tools.dbc.parse_dbc`: an uploaded DBC, read without cantools.

    The same exposure as the ARXML path -- a file a tester accepts from a
    supplier -- but parsed by hand from line shapes rather than by a library,
    which is where the docstring's promise to be "faithful about what the file
    says" has to hold on its own.
    """
    from iotsploit_django.tools.dbc import parse_dbc as target

    return target(text_input(payload))


def parse_ip_link_details(payload: bytes) -> Any:
    """`drivers.socketcan.can_link`: whatever `ip -details link show` printed.

    Output of a tool this repository does not own, on a host whose iproute2
    version it does not choose.
    """
    from iotsploit_drivers.socketcan.can_link import parse_ip_link_details as target

    return target(text_input(payload))


def decode_can_error_frame(payload: bytes) -> Any:
    """`drivers.socketcan.can_errors.decode_error_frame`: bytes off the wire."""
    from iotsploit_drivers.socketcan.can_errors import decode_error_frame as target

    if len(payload) < 4:
        raise Skip("needs four bytes of arbitration id")
    return target(int.from_bytes(payload[:4], "big"), payload[4:])


def parse_nmap_grepable(payload: bytes) -> Any:
    """`exploits.nmap_scan`: nmap's grepable output, parsed by hand."""
    from iotsploit_exploits.nmap_scan.nmap_scan import _parse_nmap_grepable as target

    return target(text_input(payload))


def parse_hosts(payload: bytes) -> Any:
    """`exploits.ip_scan.parse_hosts`: operator input, only ValueError."""
    from iotsploit_exploits.ip_scan.ip_scan import parse_hosts as target

    return target(text_input(payload))


def capture_request(payload: bytes) -> Any:
    """`exploits.canbus.live_capture.parse_request`: any JSON, only ValueError."""
    from iotsploit_exploits.canbus.live_capture import parse_request as target

    return target(text_input(payload))


def uds_parse_command(payload: bytes) -> Any:
    """`exploits.uds.interactive.parse_command`: a line someone typed.

    Its contract is that the vocabulary never gets in the way -- anything
    unrecognised is treated as raw hex rather than refused -- so nothing
    should escape it at all.
    """
    from iotsploit_exploits.uds.interactive import catalog_by_name, parse_command

    return parse_command(text_input(payload), catalog_by_name())


def did_pack(payload: bytes) -> Any:
    """`exploits.uds` DID profile pack, from the file to the parsed registry.

    The pack is an operator-installed file. ``load_did_pack`` declares
    ``ValueError`` and checks the outer shape -- a dict carrying a ``dids``
    list -- and ``definitions()`` then reads everything below it with
    unguarded subscripting: ``item["fields"]``, ``field["byte_start"]``,
    ``int(item["did"], 16)``, ``int(key)`` for every choice. The pair is the
    target, because the validation and the consumption are in different
    functions.

    Aimed at the real file by pointing the module constant at a temporary
    one. Both ``_pack`` and ``definitions`` are ``lru_cache``d, and *both*
    have to be cleared: clearing only the outer one still answers every
    payload after the first from the first one's file, which is a state leak
    a batched worker would otherwise hide completely.
    """
    from iotsploit_exploits.uds import did_registry, local_profile

    path = Path(temp_file(payload, ".json"))
    original = local_profile._DID_FILE
    local_profile._DID_FILE = path
    for cached in (did_registry._pack, did_registry.definitions):
        cached.cache_clear()
    try:
        return did_registry.definitions()
    finally:
        local_profile._DID_FILE = original
        for cached in (did_registry._pack, did_registry.definitions):
            cached.cache_clear()
        os.unlink(path)


def as_number(payload: bytes) -> Any:
    """`core.utils.as_number`: the parameter boundary every plugin sits behind.

    In the registry for the same reason ``parse_target_bits`` is: it is a
    parser this repository owns, and every declared int in every plugin now
    goes through it.
    """
    from iotsploit_core.utils import as_number as target

    return target(text_input(payload), "value", minimum=0, maximum=0xFFFF)



# -- the target document ----------------------------------------------------
#
# A target is a JSON document that arrives from an import file, an HTTP
# request, or the database, and becomes a domain object. Everything the
# toolkit does afterwards -- which buses exist, which frames a component
# sends, where an exploit is pointed -- is read off it.


def _hydrate(raw: Any) -> Any:
    """The read path from `target_models._hydrate_target`, without Django."""
    from iotsploit_core.domain.target import (
        ComponentFactory,
        Vehicle,
        fold_legacy_interfaces,
    )

    if not isinstance(raw, dict):
        raise Skip("a target document is an object")
    data = fold_legacy_interfaces(raw)
    components = [
        ComponentFactory.create_component(c) if isinstance(c, dict) else c
        for c in data.get("components") or []
    ]
    return Vehicle(
        target_id=data.get("target_id", ""),
        name=data.get("name", ""),
        type=data.get("type", "vehicle"),
        status=data.get("status", "active"),
        properties=data.get("properties") or {},
        ip_address=data.get("ip_address"),
        location=data.get("location"),
        components=components,
        buses=data.get("buses") or [],
        edges=data.get("edges") or [],
    )


def target_document(payload: bytes) -> Any:
    """A stored target document becoming a Vehicle.

    Pydantic validates, so ``ValidationError`` is the contract. Anything else
    escaping means a field reached a model that the model did not get to
    judge -- which is how a dangling edge or an unreadable component would
    become a target the rest of the toolkit trusts.
    """
    return _hydrate(json_input(payload))


def create_component(payload: bytes) -> Any:
    """`ComponentFactory.create_component`: one component of that document.

    Worth its own entry because it does not simply validate -- it sorts
    unknown keys into ``properties`` and fills defaults, so it can produce a
    component the document never described.
    """
    from iotsploit_core.domain.target import ComponentFactory

    raw = json_object(payload, "a component is an object")
    return ComponentFactory.create_component(raw)


def fold_legacy(payload: bytes) -> Any:
    """`fold_legacy_interfaces`, held to the two properties it claims.

    Its docstring states both: "folding twice is a no-op, which is what makes
    this safe to run on every read", and "returns a new dict; the argument is
    left alone". The first runs on every target read, so a fold that is not
    idempotent duplicates components on the second read; the second matters
    because the caller keeps using the dict it passed in.
    """
    from copy import deepcopy

    from iotsploit_core.domain.target import fold_legacy_interfaces

    raw = json_object(payload, "a target document is an object")

    before = deepcopy(raw)
    once = fold_legacy_interfaces(raw)
    if raw != before:
        raise MetamorphicError("fold_legacy_interfaces modified its argument")
    twice = fold_legacy_interfaces(once)
    if twice != once:
        raise MetamorphicError("folding twice is not the same as folding once")
    return once



def target_roundtrip(payload: bytes) -> Any:
    """A target saved and read back must be the same target.

    The property target *management* rests on. ``get_info`` is
    ``model_dump``, and every store and reload in the toolkit is a dump
    followed by a rehydrate -- the JSON importer, the Django repository, the
    HTTP layer. A field that does not survive that trip is not a crash: it is
    a target that quietly loses a bus, a facet, or an edge between one read
    and the next, and every answer given afterwards is about a target that no
    longer matches the vehicle.
    """
    from iotsploit_core.domain.target import Vehicle

    first = _hydrate(json_input(payload))
    dumped = first.get_info()
    try:
        second = Vehicle(**dumped)
    except Exception as error:  # noqa: BLE001 - re-reading our own dump must work
        raise MetamorphicError(
            f"a dumped target did not survive being read back: {error}"
        ) from None
    if second.get_info() != dumped:
        raise MetamorphicError("a target changed on its second round trip")
    return second


def resolve_facets(payload: bytes) -> Any:
    """`domain.facet.resolve_facets`: the open, plugin-registered half.

    Core registers no facets; plugins register their own, so this resolves
    keys it has never seen against a registry it does not control. It
    declares TypeError for a non-mapping.
    """
    from iotsploit_core.domain.facet import resolve_facets as target

    return target(json_input(payload))



# -- streaming --------------------------------------------------------------
#
# A stream message crosses a serialisation boundary twice on every hop: out to
# Redis or a WebSocket as a dict, and back again. The interesting failures on
# that path are not single-message crashes -- they are sequence and state, so
# one of these targets fuzzes an ordered session rather than one input.


def stream_message(payload: bytes) -> Any:
    """`domain.stream.StreamData.from_dict`, and its round trip.

    Every stream message is rebuilt by this from a dict that travelled through
    Redis or a socket. It reads each key by subscript and puts three of them
    through an Enum, so the contract it can hold is KeyError-free rejection --
    and a message that does not survive ``from_dict(to_dict(m))`` is one that
    arrives at the far end as something other than what was sent.
    """
    from iotsploit_core.domain.stream import StreamData

    raw = json_object(payload, "a stream message is an object")
    message = StreamData.from_dict(raw)
    again = StreamData.from_dict(message.to_dict())
    if again.to_dict() != message.to_dict():
        raise MetamorphicError("a stream message changed on its round trip")
    return message


def stream_session(payload: bytes) -> Any:
    """An ordered session against the in-memory stream backend, run async.

    The payload is a *sequence* of operations rather than one message, because
    a streaming defect is almost never one bad frame -- it is a register that
    never unregisters, a broadcast to a channel that is gone, a client queue
    that grows without a reader. Fuzzing one message at a time cannot reach
    any of those.

    Run under ``asyncio.run`` in the worker, which is all it takes to fuzz
    async code: the event loop is this process's problem, and this process is
    the one we are willing to lose.

    Three invariants are asserted at the end, all of them things the callers
    of this backend assume:

    * a channel registered and not unregistered is active
    * a channel unregistered, or never registered, is not
    * no channel is listed twice
    """
    import asyncio

    from iotsploit_core.core.stream_manager import _NoopStreamBackend
    from iotsploit_core.domain.stream import StreamData

    operations = json_input(payload)
    if not isinstance(operations, list):
        raise Skip("a session is a list of operations")

    async def drive() -> Any:
        backend = _NoopStreamBackend()
        expected: set = set()
        for step in operations[:200]:
            if not isinstance(step, dict):
                continue
            action = str(step.get("op", ""))
            channel = str(step.get("channel", ""))
            if action == "register":
                await backend.register_stream(channel)
                expected.add(channel)
            elif action == "unregister":
                await backend.unregister_stream(channel)
                expected.discard(channel)
            elif action == "broadcast":
                message = step.get("message")
                if isinstance(message, dict):
                    await backend.broadcast_data(StreamData.from_dict(message))
            elif action == "stop":
                await backend.stop_broadcast(channel)
        return backend, expected

    backend, expected = asyncio.run(drive())
    active = backend.get_active_channels()
    if len(active) != len(set(active)):
        raise MetamorphicError(f"a channel is listed twice: {sorted(active)}")
    if set(active) != expected:
        raise MetamorphicError(
            f"active channels {sorted(set(active))} are not the registered ones "
            f"{sorted(expected)}"
        )
    return active




# -- plugin services --------------------------------------------------------
#
# Everything a plugin receives crosses one of these, and everything it returns
# crosses another. The input is operator JSON over HTTP or the CLI on one
# side, and a plugin author's own code on the other.


class _Declaring:
    """A stand-in plugin carrying whatever schema the payload describes."""

    def __init__(self, declared: Any) -> None:
        self._declared = declared

    def get_info(self) -> Any:
        return {"Name": "fuzzed", "Parameters": self._declared}


class _Result:
    """An object shaped like the one a plugin returns."""

    def __init__(self, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(self, key, value)


def coerce_parameters(payload: bytes) -> Any:
    """`ExploitPluginManager._coerce_parameters`: the parameter boundary.

    Every plugin's parameters cross it, and both halves are fuzzed together
    because both can be wrong independently: the schema is written by a plugin
    author, and the values arrive from a transport that sends everything as
    text. It declares ValueError naming the parameter -- which is what the
    four hand-written copies it replaced all raised.
    """
    from iotsploit_core.core.exploit_manager import ExploitPluginManager

    raw = json_object(payload, "an object with declared and parameters")
    parameters = raw.get("parameters")
    if not isinstance(parameters, dict):
        raise Skip("parameters must be an object")
    return ExploitPluginManager._coerce_parameters(
        _Declaring(raw.get("declared")), parameters
    )


def resolve_plugin_file(payload: bytes) -> Any:
    """`ExploitPluginManager._resolve_plugin_file`: the path guard.

    A security boundary, so the contract is stronger than "does not raise":
    **whatever it returns must be inside the configured plugins directory**.
    Refusing is always allowed; returning a path that escapes the root, or one
    reached through a symlink, is not.

    The root is built fresh per payload with a real plugin in it, a nested
    directory, and a symlink pointing outside -- so a payload has something
    real to try to reach past.
    """
    import shutil
    import tempfile
    from types import SimpleNamespace

    from iotsploit_core.core.exploit_manager import ExploitPluginManager

    text = text_input(payload)
    root = Path(tempfile.mkdtemp(prefix="plugins_"))
    outside = Path(tempfile.mkdtemp(prefix="outside_"))
    try:
        (root / "real_plugin.py").write_text("# a plugin\n")
        (root / "nested").mkdir()
        (root / "nested" / "deep.py").write_text("# nested\n")
        (outside / "secret.py").write_text("# not yours\n")
        try:
            (root / "escape.py").symlink_to(outside / "secret.py")
        except OSError:
            pass

        manager = SimpleNamespace(plugins_dir=root)
        resolved = Path(ExploitPluginManager._resolve_plugin_file(manager, text))

        real_root = root.resolve()
        if not str(resolved.resolve()).startswith(str(real_root) + os.sep):
            raise MetamorphicError(
                f"accepted a path outside the plugins directory: {resolved}"
            )
        return str(resolved.resolve().relative_to(real_root))
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def format_result(payload: bytes) -> Any:
    """`ExploitPluginManager._format_result`: whatever a plugin handed back.

    It reads attributes off the result and falls back to ``str(result)``, so
    the object is the plugin author's rather than the framework's. It declares
    nothing, which means nothing should escape it.
    """
    from iotsploit_core.core.exploit_manager import ExploitPluginManager

    raw = json_input(payload)
    result: Any = _Result(**raw) if isinstance(raw, dict) and "success" in raw else raw
    provenance = raw.get("provenance") if isinstance(raw, dict) else None
    return ExploitPluginManager._format_result(result, provenance)


# ---- the registry ----


_HERE = "iotsploit_fuzzer.targets.iotsploit"

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


_DBC_SEED = 'VERSION ""\n\nBU_: ECM TCM\n\nBO_ 291 EngineStatus: 8 ECM\n SG_ Speed : 0|16@1+ (0.1,0) [0|250] "km/h" TCM\n SG_ Gear : 16|4@1+ (1,0) [0|8] "" TCM\n\nBO_ 2147483939 ExtFrame: 2 TCM\n SG_ Flag : 0|1@1+ (1,0) [0|1] "" ECM\n\nVAL_ 291 Gear 3 "Drive" 1 "Park" ;\nCM_ BU_ ECM "Engine controller";\n'

_IP_LINK_SEED = '1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT\n    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n3: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT qlen 10\n    link/can  promiscuity 0 minmtu 0 maxmtu 0\n    can state ERROR-ACTIVE restart-ms 0\n    bitrate 500000 sample-point 0.875\n    pcan_usb_fd: tseg1 1..256 tseg2 1..128 sjw 1..128 brp 1..1024 brp-inc 1\n4: can1: <NOARP,UP> mtu 72 qdisc pfifo_fast state UP mode DEFAULT qlen 10\n    link/can\n    can state ERROR-ACTIVE restart-ms 100\n    bitrate 500000 dbitrate 2000000 sample-point 0.750\n'

_NMAP_SEED = '# Nmap 7.80 scan initiated\nHost: 192.168.1.10 ()\tStatus: Up\nHost: 192.168.1.10 ()\tPorts: 22/open/tcp//ssh///, 80/open/tcp//http///\nHost: 192.168.1.11 ()\tStatus: Down\n# Nmap done\n'

_DID_PACK_SEED = _json_seed(
    {
        "schema_version": 1,
        "source": {"file": "oem.xml"},
        "dids": [
            {
                "did": "F190",
                "name": "VIN",
                "size_bytes": 17,
                "access": {"read": True, "read_security_level": 0},
                "fields": [
                    {
                        "name": "vin",
                        "byte_start": 1,
                        "byte_end": 17,
                        "bit_low": 0,
                        "bit_high": 7,
                        "choices": {"0": "none"},
                        "choice_format": "dec",
                        "description": "Vehicle identification number",
                    }
                ],
            }
        ],
    }
)

_TARGET_DOCUMENT_SEED = _json_seed(
    {
        "target_id": "t1",
        "name": "Zeekr",
        "type": "vehicle",
        "status": "active",
        "ip_address": "192.168.1.50",
        "components": [
            {"component_id": "c_vgm", "name": "VGM", "type": "ecu"},
            {"component_id": "c_tcam", "name": "TCAM", "type": "ecu", "vendor": "X"},
        ],
        "buses": [{"bus_id": "bus_can_b", "name": "CAN-B", "type": "can"}],
        "edges": [{"source": "c_vgm", "target": "bus_can_b", "relation": "bus_member"}],
    }
)

#: The shape fold_legacy_interfaces exists to migrate.
_LEGACY_TARGET_SEED = _json_seed(
    {
        "target_id": "t1",
        "name": "Zeekr",
        "components": [{"component_id": "c_vgm", "name": "VGM", "type": "ecu"}],
        "interfaces": [{"interface_id": "i_eth0", "name": "eth0", "type": "ethernet"}],
    }
)

_STREAM_MESSAGE_SEED = _json_seed(
    {
        "stream_type": "can",
        "channel": "can0",
        "timestamp": 1758240000.0,
        "source": "device",
        "action": "data",
        "data": {"frame_id": 291, "payload": "1122"},
        "metadata": None,
    }
)

_STREAM_SESSION_SEED = _json_seed(
    [
        {"op": "register", "channel": "can0"},
        {"op": "register", "channel": "can1"},
        {
            "op": "broadcast",
            "channel": "can0",
            "message": {
                "stream_type": "can", "channel": "can0", "timestamp": 1.0,
                "source": "client", "action": "data", "data": {}, "metadata": None,
            },
        },
        {"op": "stop", "channel": "can1"},
        {"op": "unregister", "channel": "can1"},
    ]
)

_COERCE_SEED = _json_seed(
    {
        "declared": {
            "port": {"type": "int", "min": 1, "max": 65535, "default": 13400},
            "enable": {"type": "bool", "default": False},
            "label": {"type": "str"},
            "ratio": {"type": "float"},
        },
        "parameters": {"port": "0x3A98", "enable": "false", "label": "x", "ratio": "2.5"},
    }
)

_RESULT_SEED = _json_seed(
    {"success": True, "message": "done", "data": {"frames": 3}, "provenance": {"source": "p"}}
)

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
        # 3: representability is decided by quantising and rebuilding the
        # value. Versions 1 and 2 both reported quantisation as a broken
        # invariant -- 1 for every value, 2 whenever the factor was large
        # enough that any value sat a fraction of a step from an integer.
        adapter_version="3",
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
    ParseTarget(
        name="django.parse_dbc",
        adapter=f"{_HERE}:parse_dbc",
        declared=(),
        seeds=(_DBC_SEED.encode(), b"", b"BO_ 1 A: 8 X\n"),
        budget_seconds=5.0,
    ),
    ParseTarget(
        name="drivers.ip_link_details",
        adapter=f"{_HERE}:parse_ip_link_details",
        declared=(),
        seeds=(_IP_LINK_SEED.encode(), b"", b"1: can0: <UP> mtu 16\n    link/can\n"),
    ),
    ParseTarget(
        name="drivers.can_error_frame",
        adapter=f"{_HERE}:decode_can_error_frame",
        declared=(),
        seeds=(
            bytes.fromhex("00000004") + b"\x00\x08\x00\x00\x00\x00\x00\x00",
            bytes.fromhex("00000040") + b"\x00\x00",
            bytes.fromhex("00000001"),
        ),
    ),
    ParseTarget(
        name="exploits.nmap_grepable",
        adapter=f"{_HERE}:parse_nmap_grepable",
        declared=(),
        seeds=(_NMAP_SEED.encode(), b"", b"Host: 10.0.0.1 ()\tPorts: 22/open/tcp//ssh///\n"),
    ),
    ParseTarget(
        name="exploits.parse_hosts",
        adapter=f"{_HERE}:parse_hosts",
        declared=("builtins:ValueError",),
        seeds=(b"192.168.1.0/24", b"10.0.0.1, 10.0.0.2", b"", b"::1"),
    ),
    ParseTarget(
        name="exploits.capture_request",
        adapter=f"{_HERE}:capture_request",
        declared=("builtins:ValueError",),
        seeds=(
            _json_seed({"schema_version": 1, "operation": "start", "bus_id": "bus-1"}),
            b"{}",
            b"",
        ),
    ),
    ParseTarget(
        name="exploits.uds_command",
        adapter=f"{_HERE}:uds_parse_command",
        declared=(),
        seeds=(b"help", b"session 3", b"22 F1 90", b"quit", b""),
    ),
    ParseTarget(
        name="exploits.did_pack",
        adapter=f"{_HERE}:did_pack",
        declared=("builtins:ValueError",),
        seeds=(_DID_PACK_SEED, b"{}", b'{"dids": []}', b'{"dids": [{}]}'),
    ),
    ParseTarget(
        name="core.as_number",
        adapter=f"{_HERE}:as_number",
        declared=("builtins:ValueError",),
        seeds=(b"0x1000", b"42", b"", b"  7 "),
        budget_seconds=2.0,
        memory_mb=512,
    ),
    ParseTarget(
        name="core.target_document",
        adapter=f"{_HERE}:target_document",
        declared=("pydantic:ValidationError",),
        seeds=(_TARGET_DOCUMENT_SEED, _LEGACY_TARGET_SEED, b"{}", b"null"),
    ),
    ParseTarget(
        name="core.create_component",
        adapter=f"{_HERE}:create_component",
        declared=("pydantic:ValidationError",),
        seeds=(
            _json_seed({"component_id": "c1", "name": "VGM", "type": "ecu"}),
            _json_seed({"component_id": "c1", "name": "N", "type": "network", "ip": "10.0.0.1"}),
            b"{}",
        ),
    ),
    ParseTarget(
        name="core.fold_legacy",
        adapter=f"{_HERE}:fold_legacy",
        declared=(),
        seeds=(_LEGACY_TARGET_SEED, _TARGET_DOCUMENT_SEED, b"{}"),
    ),
    ParseTarget(
        name="core.target_roundtrip",
        adapter=f"{_HERE}:target_roundtrip",
        declared=("pydantic:ValidationError",),
        seeds=(_TARGET_DOCUMENT_SEED, _LEGACY_TARGET_SEED),
    ),
    ParseTarget(
        name="core.resolve_facets",
        adapter=f"{_HERE}:resolve_facets",
        declared=("builtins:TypeError",),
        seeds=(
            _json_seed({"can": {"messages": []}}),
            _json_seed({}),
            b"null",
            b"[]",
        ),
    ),
    ParseTarget(
        name="core.stream_message",
        adapter=f"{_HERE}:stream_message",
        declared=("builtins:KeyError", "builtins:ValueError"),
        seeds=(_STREAM_MESSAGE_SEED, b"{}", _json_seed({"stream_type": "nope"})),
    ),
    ParseTarget(
        name="core.stream_session",
        adapter=f"{_HERE}:stream_session",
        declared=("builtins:KeyError", "builtins:ValueError"),
        seeds=(_STREAM_SESSION_SEED, b"[]", _json_seed([{"op": "unregister", "channel": "ghost"}])),
        budget_seconds=10.0,
    ),
    ParseTarget(
        name="plugins.coerce_parameters",
        adapter=f"{_HERE}:coerce_parameters",
        declared=("builtins:ValueError",),
        seeds=(_COERCE_SEED, b'{"declared": {}, "parameters": {}}'),
    ),
    ParseTarget(
        name="plugins.resolve_plugin_file",
        adapter=f"{_HERE}:resolve_plugin_file",
        declared=("builtins:ValueError",),
        seeds=(b"real_plugin.py", b"../../etc/passwd", b"escape.py", b""),
    ),
    ParseTarget(
        name="plugins.format_result",
        adapter=f"{_HERE}:format_result",
        declared=(),
        seeds=(_RESULT_SEED, b'{"message": "plain"}', b"null", b"[]"),
    ),
):
    register(_target)

del _target
