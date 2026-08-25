"""Turning a target into CAN frame definitions, and refusing to guess.

A target stores CAN frames in two places. ARXML frames and DBC frames with no
declared transmitter live under ``bus.properties.messages``; DBC frames that
name a sender live under ``component.facets.can.messages``, with the facet's
``bus_id`` saying which bus they belong to. Both describe the same wire.

This module reads both and produces one shape. It never reads the database, the
current target, or the environment -- a mapping goes in and definitions come
out -- which is what lets the same code run under a plugin, a test, or a
capture loop.

Two rules are load-bearing and easy to get wrong:

*Identity is ``(bus_id, frame_id, is_extended)``.* Not a name: the same frame
name legitimately appears on two buses, and a standard 0x123 and an extended
0x123 are different frames sharing a wire. A resolver keyed on a name or on a
bare number answers confidently and wrongly.

*Disagreement is a finding, not a tie to break.* When two rows claim one
identity and describe different bytes, this marks the frame conflicted and
every caller refuses it. Picking the first would silently transmit one
document's idea of a frame while the operator read the other's.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from iotsploit_protocols.canbus.definitions import (
    BusDefinition,
    FrameDefinition,
    SignalDefinition,
    frame_id_is_valid,
)
from iotsploit_protocols.canbus.errors import CanDefinitionError

#: The payload lengths CAN FD allows. Classic CAN is 0..8 contiguous; FD keeps
#: those and then jumps, so a 9-byte FD frame does not exist.
FD_PAYLOAD_LENGTHS = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64})

CAN_FACET_KEY = "can"


def _field(source: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` off a mapping or an object.

    Targets arrive as pydantic models from the Django path and as plain dicts
    from the Celery and MCP paths. Handling both here keeps every caller from
    having to know which one it got.
    """
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _as_int(value: Any) -> Optional[int]:
    """An int, or ``None`` when the value is not one.

    Deliberately strict about ``bool``: Python makes ``True`` an ``int``, and a
    frame id of ``True`` would resolve as frame 1.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 16) if text.lower().startswith("0x") else int(text)
        except ValueError:
            return None
    return None


def _signal_from(raw: Any) -> SignalDefinition:
    """One stored signal, in whichever of the two shapes it was written."""
    choices_raw = _field(raw, "choices") or None
    choices: Optional[Dict[int, str]] = None
    if isinstance(choices_raw, Mapping):
        # The ARXML importer stringifies mapping keys on its way to JSON, so
        # "0" and 0 arrive as different keys for one code unless normalized.
        converted = {}
        for key, label in choices_raw.items():
            code = _as_int(key)
            if code is not None:
                converted[code] = str(label)
        choices = converted or None

    byte_order = str(_field(raw, "byte_order", "little") or "little")
    return SignalDefinition(
        name=str(_field(raw, "name", "") or ""),
        start_bit=_as_int(_field(raw, "start_bit", 0)) or 0,
        length=_as_int(_field(raw, "length", 0)) or 0,
        byte_order="big" if byte_order.startswith("big") else "little",
        signed=bool(_field(raw, "signed", False)),
        factor=float(_field(raw, "factor", 1.0) or 1.0),
        offset=float(_field(raw, "offset", 0.0) or 0.0),
        minimum=_optional_float(_field(raw, "minimum")),
        maximum=_optional_float(_field(raw, "maximum")),
        unit=str(_field(raw, "unit", "") or ""),
        multiplexer=_optional_str(_field(raw, "multiplexer")),
        multiplexer_signal=_optional_str(_field(raw, "multiplexer_signal")),
        choices=choices,
        is_float=bool(_field(raw, "is_float", False)),
    )


def _optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _frame_from(
    raw: Any,
    *,
    bus_id: str,
    owner_kind: str,
    index: int,
    component_id: Optional[str] = None,
    component_name: Optional[str] = None,
) -> FrameDefinition:
    """One stored frame, with its unsupported reason already worked out."""
    frame_id = _as_int(_field(raw, "frame_id"))
    is_extended = bool(_field(raw, "is_extended", False))
    signals = tuple(_signal_from(s) for s in (_field(raw, "signals") or ()))
    contained = tuple(
        c for c in (_field(raw, "contained_messages") or ()) if isinstance(c, Mapping)
    )
    dlc = _as_int(_field(raw, "dlc", 0)) or 0
    is_fd = bool(_field(raw, "is_fd", False))

    frame = FrameDefinition(
        bus_id=bus_id,
        frame_id=frame_id if frame_id is not None else -1,
        is_extended=is_extended,
        name=str(_field(raw, "name", "") or ""),
        dlc=dlc,
        signals=signals,
        is_fd=is_fd,
        senders=tuple(str(s) for s in (_field(raw, "senders") or ())),
        cycle_time_ms=_as_int(_field(raw, "cycle_time_ms")),
        owner_kind=owner_kind,
        component_id=component_id,
        component_name=component_name,
        source_index=index,
        contained_messages=contained,
    )
    reason = _unsupported_reason(frame, raw_frame_id=frame_id)
    if reason is None:
        return frame
    return FrameDefinition(**{**frame.__dict__, "unsupported_reason": reason})


def _unsupported_reason(frame: FrameDefinition, *, raw_frame_id: Optional[int]) -> Optional[str]:
    """Why this frame cannot be composed, or ``None`` when it can.

    Only the structural checks live here. Whether a signal actually fits inside
    the payload is ``cantools``' answer, given at encode time, because a second
    implementation of bit-layout rules would eventually disagree with the one
    doing the packing.
    """
    if raw_frame_id is None:
        return "frame has no usable numeric id"
    if not frame_id_is_valid(frame.frame_id, frame.is_extended):
        width = "29-bit extended" if frame.is_extended else "11-bit standard"
        return f"frame id 0x{frame.frame_id:X} does not fit a {width} identifier"
    if frame.contained_messages:
        return (
            f"container frame carrying {len(frame.contained_messages)} contained PDUs; "
            "header selection and per-PDU encoding are not supported"
        )
    if frame.is_fd:
        if frame.dlc not in FD_PAYLOAD_LENGTHS:
            return f"CAN FD has no {frame.dlc}-byte payload length"
    elif frame.dlc > 8:
        return f"classic CAN carries at most 8 bytes, not {frame.dlc}"

    return _multiplexing_reason(frame)


def _multiplexing_reason(frame: FrameDefinition) -> Optional[str]:
    """Whether the frame's multiplexing is complete and self-consistent."""
    switches = [s.name for s in frame.signals if s.is_multiplexer]
    branches = [s for s in frame.signals if s.multiplexer_ids]

    if len(switches) > 1:
        return f"frame declares {len(switches)} multiplexer switches: {', '.join(sorted(switches))}"
    if branches and not switches:
        names = ", ".join(sorted(s.name for s in branches)[:3])
        return f"multiplexed signals ({names}) but no signal is marked as the switch"
    if switches and not branches:
        # A switch nobody branches on is odd but encodable: it is just an
        # ordinary field. Saying so beats refusing a frame that works.
        return None
    for signal in branches:
        if signal.multiplexer_signal and switches and signal.multiplexer_signal != switches[0]:
            return (
                f"signal {signal.name!r} is multiplexed by {signal.multiplexer_signal!r}, "
                f"which is not this frame's switch {switches[0]!r}"
            )
    return None


def _bus_rows(target: Any) -> List[Any]:
    return list(_field(target, "buses") or ())


def _component_rows(target: Any) -> List[Any]:
    return list(_field(target, "components") or ())


def _can_facet_of(component: Any) -> Optional[Any]:
    facets = _field(component, "facets") or {}
    if isinstance(facets, Mapping):
        return facets.get(CAN_FACET_KEY)
    return getattr(facets, CAN_FACET_KEY, None)


class TargetCanCatalog:
    """Every CAN frame a target documents, indexed by bus and identity.

    Built once per target snapshot and then read many times. A capture loop
    resolving per frame at thousands of frames a second is the difference
    between keeping up and dropping traffic, so nothing here is lazy.
    """

    def __init__(self, buses: Sequence[BusDefinition], target_id: Optional[str] = None) -> None:
        self._buses: Tuple[BusDefinition, ...] = tuple(buses)
        self._by_id: Dict[str, BusDefinition] = {bus.bus_id: bus for bus in self._buses}
        self.target_id = target_id

    @classmethod
    def from_target(cls, target: Any) -> "TargetCanCatalog":
        """Read a target mapping or model into a catalogue.

        The argument is never modified. Buses that are not CAN are skipped
        rather than rejected: an Ethernet segment on the same target is not an
        error, it is simply not ours.
        """
        if target is None:
            raise CanDefinitionError("no target supplied")

        components = _component_rows(target)
        buses: List[BusDefinition] = []

        for bus in _bus_rows(target):
            if str(_field(bus, "type", "") or "").lower() != "can":
                continue
            bus_id = str(_field(bus, "bus_id", "") or "")
            if not bus_id:
                continue

            collected: List[FrameDefinition] = []

            properties = _field(bus, "properties") or {}
            for index, raw in enumerate(_field(properties, "messages") or ()):
                collected.append(_frame_from(raw, bus_id=bus_id, owner_kind="bus", index=index))

            for component in components:
                facet = _can_facet_of(component)
                if facet is None:
                    continue
                if str(_field(facet, "bus_id", "") or "") != bus_id:
                    continue
                component_id = _optional_str(_field(component, "component_id"))
                component_name = _optional_str(_field(component, "name"))
                for index, raw in enumerate(_field(facet, "messages") or ()):
                    collected.append(
                        _frame_from(
                            raw,
                            bus_id=bus_id,
                            owner_kind="component",
                            index=index,
                            component_id=component_id,
                            component_name=component_name,
                        )
                    )

            frames, conflicts = _resolve_duplicates(collected)
            buses.append(
                BusDefinition(
                    bus_id=bus_id,
                    name=str(_field(bus, "name", bus_id) or bus_id),
                    frames=tuple(frames),
                    conflicts=tuple(conflicts),
                )
            )

        return cls(buses, target_id=_optional_str(_field(target, "target_id")))

    @property
    def buses(self) -> Tuple[BusDefinition, ...]:
        return self._buses

    def bus(self, bus_id: str) -> BusDefinition:
        """The named CAN bus, or a failure that says which ids do exist."""
        found = self._by_id.get(bus_id)
        if found is None:
            known = ", ".join(sorted(self._by_id)) or "none"
            raise CanDefinitionError(
                f"target has no CAN bus {bus_id!r} (CAN buses on this target: {known})"
            )
        return found

    def frames(self, bus_id: str) -> Tuple[FrameDefinition, ...]:
        return self.bus(bus_id).frames

    def resolve(
        self,
        bus_id: str,
        frame_id: int,
        is_extended: bool = False,
        *,
        expected_name: Optional[str] = None,
    ) -> FrameDefinition:
        """The one frame matching this identity, or a stated reason it is not usable.

        ``expected_name`` is a staleness check, never a lookup key. A form built
        against a target that has since been re-imported may hold a name that no
        longer belongs to this id, and encoding it anyway would send the right
        bytes for the wrong frame.
        """
        bus = self.bus(bus_id)

        if not frame_id_is_valid(frame_id, is_extended):
            width = "29-bit extended" if is_extended else "11-bit standard"
            raise CanDefinitionError(
                f"frame id {frame_id!r} does not fit a {width} identifier"
            )

        if _identity_key(frame_id, is_extended) in bus.conflicts:
            raise CanDefinitionError(
                f"frame 0x{frame_id:X} on bus {bus_id!r} has conflicting definitions "
                "that disagree on how to encode it; fix the target before sending"
            )

        frame = bus.frame(frame_id, is_extended)
        if frame is None:
            kind = "extended" if is_extended else "standard"
            raise CanDefinitionError(
                f"bus {bus_id!r} documents no {kind} frame 0x{frame_id:X}"
            )

        if expected_name and frame.name != expected_name:
            raise CanDefinitionError(
                f"frame 0x{frame_id:X} on bus {bus_id!r} is {frame.name!r}, "
                f"not {expected_name!r}; the target changed since this form was built"
            )

        if not frame.is_supported:
            raise CanDefinitionError(
                f"frame {frame.name!r} (0x{frame_id:X}) cannot be composed: "
                f"{frame.unsupported_reason}"
            )

        return frame


def _identity_key(frame_id: int, is_extended: bool) -> str:
    return f"{'x' if is_extended else 's'}{frame_id:X}"


def _resolve_duplicates(
    frames: Iterable[FrameDefinition],
) -> Tuple[List[FrameDefinition], List[str]]:
    """Collapse identical definitions and mark incompatible ones as conflicts.

    Two components declaring the same frame the same way is ordinary and
    deduplicates silently. Two documents describing one identity differently is
    a fact about the target that no caller may paper over, so the frame is
    still listed -- with a reason -- and every attempt to use it fails.
    """
    grouped: Dict[Tuple[int, bool], List[FrameDefinition]] = {}
    for frame in frames:
        grouped.setdefault((frame.frame_id, frame.is_extended), []).append(frame)

    resolved: List[FrameDefinition] = []
    conflicts: List[str] = []

    for (frame_id, is_extended), candidates in grouped.items():
        distinct: List[FrameDefinition] = []
        for candidate in candidates:
            if not any(candidate.encoding_key() == kept.encoding_key() for kept in distinct):
                distinct.append(candidate)

        if len(distinct) == 1:
            resolved.append(distinct[0])
            continue

        conflicts.append(_identity_key(frame_id, is_extended))
        sources = ", ".join(sorted(_describe_source(f) for f in distinct))
        first = distinct[0]
        resolved.append(
            FrameDefinition(
                **{
                    **first.__dict__,
                    "unsupported_reason": (
                        f"{len(distinct)} incompatible definitions for this identity "
                        f"({sources}); the target has to say which one is right"
                    ),
                }
            )
        )

    resolved.sort(key=lambda f: (f.frame_id, f.is_extended))
    return resolved, conflicts


def _describe_source(frame: FrameDefinition) -> str:
    if frame.owner_kind == "component":
        who = frame.component_name or frame.component_id or "unnamed component"
        return f"{frame.name!r} from {who}"
    return f"{frame.name!r} from the bus"
