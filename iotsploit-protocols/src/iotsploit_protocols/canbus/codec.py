"""Physical signal values to bytes, and bytes back to physical signal values.

``cantools`` is the authority on bit placement, and this module's job is to
hand it a faithfully reconstructed message and get out of the way. Big-endian
straddling, signed two's complement across a byte boundary, and multiplexed
layouts are exactly the places a hand-rolled packer looks right and is wrong,
which is why none of that arithmetic appears here.

Encoding and decoding share one reconstruction on purpose. The inverse costs a
function rather than a module, and it buys evidence a golden vector cannot: a
round trip proves the layout, whereas a hand-written vector and a mistaken
encoder can agree while both misplace the same bits.

They are not symmetric, though, and the asymmetry is the point:

* Encoding is strict. An unknown signal name, a missing active signal, or an
  out-of-range value is an operator error and fails loudly.
* Decoding never raises for bad data. Its input came off a wire and is not
  trusted, so a malformed payload returns a described failure. A capture that
  dies on one corrupt frame is not a capture.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping, Optional, Tuple

from cantools.database.can.message import Message
from cantools.database.can.signal import Signal
from cantools.database.conversion import BaseConversion

from iotsploit_protocols.canbus.definitions import (
    DecodedFrame,
    EncodedFrame,
    FrameDefinition,
    SignalDefinition,
)
from iotsploit_protocols.canbus.errors import CanDefinitionError, CanValueError


def build_message(definition: FrameDefinition) -> Message:
    """Reconstruct the ``cantools`` message this definition describes.

    ``strict=True`` is what makes a signal reaching past the payload a failure
    here rather than a silently truncated frame on the wire. The catalogue does
    the cheap structural checks; this is where the layout itself is judged, by
    the same library that will pack it.
    """
    if definition.contained_messages:
        raise CanDefinitionError(
            f"frame {definition.name!r} is a container frame and cannot be encoded"
        )

    signals = [_build_signal(s) for s in definition.signals]
    try:
        return Message(
            frame_id=definition.frame_id,
            name=definition.name or f"frame_{definition.frame_id:X}",
            length=definition.dlc,
            signals=signals,
            is_extended_frame=definition.is_extended,
            is_fd=definition.is_fd,
            senders=list(definition.senders) or None,
            cycle_time=definition.cycle_time_ms,
            strict=True,
        )
    except Exception as error:
        # cantools raises its own error types for overlapping and overlong
        # layouts. Re-spelled here so a caller catches one name, and with the
        # frame named because "signal does not fit" alone is undiagnosable.
        raise CanDefinitionError(
            f"frame {definition.name!r} (0x{definition.frame_id:X}) has an unusable "
            f"layout: {error}"
        ) from error


def _build_signal(definition: SignalDefinition) -> Signal:
    conversion = BaseConversion.factory(
        scale=definition.factor,
        offset=definition.offset,
        choices=dict(definition.choices) if definition.choices else None,
        is_float=definition.is_float,
    )
    return Signal(
        name=definition.name,
        start=definition.start_bit,
        length=definition.length,
        byte_order="big_endian" if definition.byte_order == "big" else "little_endian",
        is_signed=definition.signed,
        conversion=conversion,
        minimum=definition.minimum,
        maximum=definition.maximum,
        unit=definition.unit or None,
        is_multiplexer=definition.is_multiplexer,
        multiplexer_ids=list(definition.multiplexer_ids) or None,
        multiplexer_signal=definition.multiplexer_signal,
    )


class CanCodec:
    """A codec that remembers the messages it has already reconstructed.

    Rebuilding a ``cantools`` message per frame at a few thousand frames a
    second is the difference between a capture that keeps up and one that drops
    traffic. The cache is keyed on the definition's own encoding fields, never
    on a target id, so a target edited underneath it cannot serve a stale
    layout.
    """

    def __init__(self) -> None:
        self._messages: Dict[Tuple[Any, ...], Message] = {}

    def message(self, definition: FrameDefinition) -> Message:
        key = definition.encoding_key()
        message = self._messages.get(key)
        if message is None:
            message = build_message(definition)
            self._messages[key] = message
        return message

    def encode(
        self, definition: FrameDefinition, values: Mapping[str, Any]
    ) -> EncodedFrame:
        return encode_frame(definition, values, message=self.message(definition))

    def decode(self, definition: FrameDefinition, data: bytes) -> DecodedFrame:
        return decode_frame(definition, data, message=self.message(definition))


def encode_frame(
    definition: FrameDefinition,
    values: Mapping[str, Any],
    *,
    message: Optional[Message] = None,
) -> EncodedFrame:
    """Pack physical signal values into the frame's payload.

    Every signal active for the selected multiplexer branch must be supplied.
    Nothing is defaulted to zero: a frame sent with an unstated field silently
    filled in is a frame the operator did not compose, and on a live bus that
    distinction is the whole point.
    """
    message = message or build_message(definition)
    if not isinstance(values, Mapping):
        raise CanValueError("signal values must be supplied as a mapping of name to value")

    active, field_errors = _active_signals(definition, values)
    if field_errors:
        raise CanValueError(_summarize(field_errors), field_errors)

    normalized: Dict[str, Any] = {}
    for name in active:
        signal = definition.signal(name)
        assert signal is not None  # active names come from the definition
        try:
            normalized[name] = _coerce(signal, values[name])
        except CanValueError as error:
            field_errors[f"signals.{name}"] = str(error)

    if field_errors:
        raise CanValueError(_summarize(field_errors), field_errors)

    try:
        data = message.encode(normalized, scaling=True, strict=True)
    except Exception as error:
        # cantools reports the offending signal in its message but not as
        # structured data, so the whole frame carries the failure and the
        # editor shows it above the rows rather than against a guessed one.
        raise CanValueError(f"frame {definition.name!r} could not be encoded: {error}") from error

    return EncodedFrame(
        frame_id=definition.frame_id,
        is_extended=definition.is_extended,
        is_fd=definition.is_fd,
        dlc=len(data),
        data=bytes(data),
        name=definition.name,
        signals=_readable(normalized),
    )


def decode_frame(
    definition: FrameDefinition,
    data: bytes,
    *,
    message: Optional[Message] = None,
) -> DecodedFrame:
    """Read a payload into named physical values.

    Returns a failure rather than raising, for every kind of bad input. The
    multiplexer branch is chosen from the bytes themselves and never from a
    caller's claim about which branch this is -- a decoder that takes that on
    trust reports one branch's names over another branch's bits.
    """
    try:
        message = message or build_message(definition)
    except CanDefinitionError as error:
        return DecodedFrame.failed(definition.name, str(error))

    if data is None:
        return DecodedFrame.failed(definition.name, "no payload to decode")
    payload = bytes(data)

    if len(payload) != definition.dlc:
        # Stated, not silently padded or truncated: a frame arriving shorter
        # than its definition is a finding about the bus or the definition, and
        # decoding the bytes that are there would hide it.
        return DecodedFrame.failed(
            definition.name,
            f"payload is {len(payload)} bytes, definition declares {definition.dlc}",
        )

    try:
        named = message.decode(payload, decode_choices=True, scaling=True)
        raw = message.decode(payload, decode_choices=False, scaling=False)
    except Exception as error:
        return DecodedFrame.failed(definition.name, f"{type(error).__name__}: {error}")

    if not isinstance(named, Mapping) or not isinstance(raw, Mapping):
        return DecodedFrame.failed(definition.name, "decoder returned no signal values")

    signals = _readable(named)
    raw_values = {
        key: int(value)
        for key, value in raw.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

    # A code the value table does not label decodes to its number, and saying
    # so beats reporting a bare integer that looks like a scaled value.
    unlabelled = sorted(
        name
        for name, value in signals.items()
        if _has_choices(definition, name) and not isinstance(value, str)
    )
    reason = (
        "no label for the value of " + ", ".join(unlabelled) if unlabelled else None
    )

    return DecodedFrame(
        ok=True,
        name=definition.name,
        signals=signals,
        raw_values=raw_values,
        reason=reason,
    )


def _has_choices(definition: FrameDefinition, name: str) -> bool:
    signal = definition.signal(name)
    return bool(signal and signal.choices)


def _active_signals(
    definition: FrameDefinition, values: Mapping[str, Any]
) -> Tuple[Tuple[str, ...], Dict[str, str]]:
    """Which signals this frame needs, given the multiplexer value supplied.

    Returns the required names and any errors about the *set* of values --
    missing, unknown, or belonging to a branch that is not selected. Errors
    about a value itself are raised later, once the set is known to be right.
    """
    errors: Dict[str, str] = {}
    switch_name = definition.multiplexer_signal_name

    common = tuple(s.name for s in definition.signals if not s.multiplexer_ids)
    active = list(common)
    selected: Optional[int] = None

    if switch_name is not None:
        if switch_name not in values:
            # Resolved before anything else because which signals are even
            # required depends on the answer.
            errors[f"signals.{switch_name}"] = (
                "the multiplexer value is required before the other signals are known"
            )
            return tuple(active), errors

        switch = definition.signal(switch_name)
        assert switch is not None
        try:
            selected = _raw_choice(switch, values[switch_name])
        except CanValueError as error:
            errors[f"signals.{switch_name}"] = str(error)
            return tuple(active), errors

        branch = [s.name for s in definition.signals if selected in s.multiplexer_ids]
        active.extend(branch)

    active_set = set(active)

    for name in active:
        if name not in values:
            errors[f"signals.{name}"] = "required"

    for name in values:
        if name in active_set:
            continue
        signal = definition.signal(name)
        if signal is None:
            errors[f"signals.{name}"] = f"frame {definition.name!r} has no signal by this name"
        elif selected is not None:
            branches = ", ".join(f"{i}" for i in signal.multiplexer_ids)
            errors[f"signals.{name}"] = (
                f"only present when {switch_name} is {branches}, not {selected}"
            )
        else:
            errors[f"signals.{name}"] = "not active for this frame"

    return tuple(active), errors


def _raw_choice(signal: SignalDefinition, value: Any) -> int:
    """The integer behind a multiplexer value, whether given as a label or a number."""
    if isinstance(value, str) and signal.choices:
        for code, label in signal.choices.items():
            if label == value:
                return code
    coerced = _coerce(signal, value)
    if isinstance(coerced, str):
        raise CanValueError(f"{value!r} is not a value of this multiplexer")
    try:
        return int(coerced)
    except (TypeError, ValueError):
        raise CanValueError(f"{value!r} is not a whole number") from None


def _coerce(signal: SignalDefinition, value: Any) -> Any:
    """One operator-supplied value, normalized without losing precision.

    Numbers arrive as strings from the editor deliberately: Dart rounds an
    integer wider than 53 bits before it ever reaches JSON, so the text is
    parsed here instead. ``Decimal`` does that parse exactly, and only becomes
    a float when the signal's own scaling means it has to.
    """
    if value is None:
        raise CanValueError("required")

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise CanValueError("required")
        if signal.choices and any(label == text for label in signal.choices.values()):
            return text
        try:
            number = Decimal(text)
        except InvalidOperation:
            if signal.choices:
                known = ", ".join(sorted(signal.choices.values()))
                raise CanValueError(f"{text!r} is not one of: {known}") from None
            raise CanValueError(f"{text!r} is not a number") from None
        return _from_decimal(number)

    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value

    raise CanValueError(f"{type(value).__name__} is not a usable signal value")


def _from_decimal(number: Decimal) -> Any:
    """An int when the text was integral, else a float.

    Keeping integers as ``int`` is what preserves a 64-bit value: routing it
    through ``float`` would round it in the last bits and encode a number the
    operator never typed.
    """
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _readable(values: Mapping[str, Any]) -> Dict[str, Any]:
    """Signal values as JSON-friendly types.

    ``cantools`` returns ``NamedSignalValue`` for a labelled code, which is not
    a ``str`` and is not JSON serializable, so a response built straight from a
    decode result fails at the transport rather than here.
    """
    readable: Dict[str, Any] = {}
    for name, value in values.items():
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            readable[name] = value
        elif isinstance(value, bool):
            readable[name] = int(value)
        else:
            readable[name] = str(value)
    return readable


def _summarize(field_errors: Mapping[str, str]) -> str:
    names = sorted(key.split(".", 1)[-1] for key in field_errors)
    if len(names) == 1:
        return f"signal {names[0]}: {list(field_errors.values())[0]}"
    return f"{len(names)} signals need attention: {', '.join(names)}"
