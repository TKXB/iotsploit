"""What a target says about one CAN frame, frozen and free of storage detail.

A target holds CAN frames in two places for historical reasons: ARXML frames
and transmitter-less DBC frames sit under ``bus.properties.messages``, while
transmitter-attributed DBC frames sit under ``component.facets.can.messages``.
Those are different JSON shapes describing the same wire, and every consumer
that reads them directly grows its own opinion about which fields exist.

These types are the single shape everything downstream works in. The catalogue
converts both storage forms into them once; the codec, the composer plugin, the
live capture, and the UI all read them and never touch the raw target again.

Nothing here validates a bit layout. That is the codec's job, because the
authority on whether a signal fits is ``cantools``, and duplicating its rules
here would produce a second answer to the same question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

#: Frame ids wider than these cannot be put on a wire. Standard CAN carries an
#: 11-bit identifier and extended CAN a 29-bit one.
MAX_STANDARD_FRAME_ID = 0x7FF
MAX_EXTENDED_FRAME_ID = 0x1FFFFFFF


@dataclass(frozen=True)
class SignalDefinition:
    """One field packed into a frame's payload.

    Carries everything needed to rebuild a ``cantools`` signal and nothing that
    only describes where it was stored. ``factor`` and ``offset`` convert raw
    to physical: ``physical = raw * factor + offset``.
    """

    name: str
    start_bit: int
    length: int
    #: ``"little"`` (Intel, DBC ``@1``) or ``"big"`` (Motorola, DBC ``@0``).
    byte_order: str = "little"
    signed: bool = False
    factor: float = 1.0
    offset: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    #: ``"M"`` for the switch, ``"m3"`` or ``"m3,m4"`` for a branch signal.
    multiplexer: Optional[str] = None
    #: Which switch selects this branch signal. Only load-bearing when a frame
    #: has more than one multiplexer, but stored always so it never has to be
    #: inferred from position.
    multiplexer_signal: Optional[str] = None
    choices: Optional[Mapping[int, str]] = None
    is_float: bool = False

    @property
    def is_multiplexer(self) -> bool:
        """Whether this signal selects which branch signals are present."""
        return self.multiplexer == "M"

    @property
    def multiplexer_ids(self) -> Tuple[int, ...]:
        """The switch values this signal is present for.

        Empty for ordinary signals and for the switch itself. ARXML joins
        several with commas because one signal can belong to more than one
        branch; DBC only ever writes a single value.
        """
        if not self.multiplexer or self.multiplexer == "M":
            return ()
        ids = []
        for token in self.multiplexer.split(","):
            token = token.strip()
            if token.startswith("m") and token[1:].lstrip("-").isdigit():
                ids.append(int(token[1:]))
        return tuple(ids)


@dataclass(frozen=True)
class FrameDefinition:
    """One frame on one bus, with where it came from attached.

    ``(bus_id, frame_id, is_extended)`` is the identity. A name is not: the
    same name legitimately appears on two buses, and 0x123 standard and 0x123
    extended are different frames sharing a wire.

    ``unsupported_reason`` is set rather than raised so that a frame the
    composer cannot encode is still listable. The UI shows it as a disabled row
    explaining itself, which is more useful than omitting it and leaving the
    operator to wonder where it went.
    """

    bus_id: str
    frame_id: int
    is_extended: bool
    name: str
    dlc: int
    signals: Tuple[SignalDefinition, ...] = ()
    is_fd: bool = False
    senders: Tuple[str, ...] = ()
    cycle_time_ms: Optional[int] = None
    #: ``"bus"`` or ``"component"`` -- which storage location this came from.
    owner_kind: str = "bus"
    component_id: Optional[str] = None
    component_name: Optional[str] = None
    #: Index in the list it was read from, so a diagnostic can point at the row.
    source_index: int = 0
    #: AUTOSAR container payloads, kept only to detect and refuse one.
    contained_messages: Tuple[Mapping[str, Any], ...] = ()
    unsupported_reason: Optional[str] = None

    @property
    def is_supported(self) -> bool:
        return self.unsupported_reason is None

    @property
    def frame_id_hex(self) -> str:
        return f"0x{self.frame_id:X}"

    @property
    def multiplexer_signal_name(self) -> Optional[str]:
        """The name of this frame's switch signal, if it has one."""
        for signal in self.signals:
            if signal.is_multiplexer:
                return signal.name
        return None

    def signal(self, name: str) -> Optional[SignalDefinition]:
        for signal in self.signals:
            if signal.name == name:
                return signal
        return None

    def encoding_key(self) -> Tuple[Any, ...]:
        """Everything that changes the bytes on the wire, and nothing else.

        Two rows describing one frame are duplicates when this matches. Where
        they came from, who sends them, and how often deliberately do not
        appear: two components declaring the same frame identically is
        ordinary, and treating that as a conflict would make half the DBCs in
        the world unusable.
        """
        return (
            self.frame_id,
            self.is_extended,
            self.is_fd,
            self.name,
            self.dlc,
            tuple(
                (
                    s.name,
                    s.start_bit,
                    s.length,
                    s.byte_order,
                    s.signed,
                    s.factor,
                    s.offset,
                    s.unit,
                    s.multiplexer,
                    s.multiplexer_signal,
                    s.is_float,
                    tuple(sorted((s.choices or {}).items())),
                )
                for s in self.signals
            ),
            bool(self.contained_messages),
        )


@dataclass(frozen=True)
class BusDefinition:
    """A CAN bus and the frames resolved onto it."""

    bus_id: str
    name: str
    frames: Tuple[FrameDefinition, ...] = ()
    #: Identities that resolved to more than one incompatible definition.
    #: Listed separately because they are findings about the target, not
    #: frames anyone can use.
    conflicts: Tuple[str, ...] = ()

    def frame(self, frame_id: int, is_extended: bool) -> Optional[FrameDefinition]:
        for candidate in self.frames:
            if candidate.frame_id == frame_id and candidate.is_extended == is_extended:
                return candidate
        return None


@dataclass(frozen=True)
class EncodedFrame:
    """The bytes a frame encodes to, with the flags needed to put them on a wire."""

    frame_id: int
    is_extended: bool
    is_fd: bool
    dlc: int
    data: bytes
    name: str
    #: Values after normalization: choice labels resolved, numeric text parsed,
    #: nothing echoed back as the operator typed it.
    signals: Dict[str, Any] = field(default_factory=dict)

    @property
    def data_hex(self) -> str:
        return self.data.hex().upper()


@dataclass(frozen=True)
class DecodedFrame:
    """The result of reading bytes against a definition.

    Never raised, always returned, because the bytes come off a wire and a
    capture that dies on one malformed frame is not a capture. ``ok`` says
    which half of this object is meaningful.
    """

    ok: bool
    name: str
    signals: Dict[str, Any] = field(default_factory=dict)
    #: Raw integers behind any named choice, so a code missing from the value
    #: table is reported as the number it was rather than lost.
    raw_values: Dict[str, int] = field(default_factory=dict)
    reason: Optional[str] = None

    @classmethod
    def failed(cls, name: str, reason: str) -> "DecodedFrame":
        return cls(ok=False, name=name, reason=reason)


def canonical_frame_id(frame_id: int, is_extended: bool = False) -> str:
    """The string form of a frame id, matching the CAN facet's own function.

    Duplicated from ``iotsploit_django.tools.can_facet`` on purpose: this
    package must not import Django, and an observation's ``subject_id`` has to
    join across both. Uppercase hex, no ``0x``, zero-padded to the width of the
    id space -- three digits standard, eight extended -- so a standard 0x123
    and an extended 0x123 stay distinct keys.
    """
    return f"{frame_id:0{8 if is_extended else 3}X}"


def frame_id_is_valid(frame_id: int, is_extended: bool) -> bool:
    """Whether a frame id fits the identifier width it claims."""
    if not isinstance(frame_id, int) or isinstance(frame_id, bool) or frame_id < 0:
        return False
    return frame_id <= (MAX_EXTENDED_FRAME_ID if is_extended else MAX_STANDARD_FRAME_ID)


def signals_by_name(signals: Sequence[SignalDefinition]) -> Dict[str, SignalDefinition]:
    return {signal.name: signal for signal in signals}
