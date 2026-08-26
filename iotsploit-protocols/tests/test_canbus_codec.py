"""Packing target-defined signals into bytes, and reading them back out.

The encode/decode round trip is the load-bearing test here, and it is stronger
than a table of golden vectors: a vector and a mistaken encoder can agree while
both misplace the same bits, whereas a round trip through an independent
decoder cannot. The two hand-checkable vectors below are kept anyway, because a
round trip alone would also pass if both directions were wrong in the same way.

The asymmetry between the two directions is deliberate and tested:

* encoding refuses anything it was not given exactly -- no defaults, no
  inactive branch values, no unknown names;
* decoding never raises, because its input came off a wire.
"""

from __future__ import annotations

import pytest

from iotsploit_protocols.canbus import TargetCanCatalog, decode_frame, encode_frame
from iotsploit_protocols.canbus.codec import CanCodec, build_message
from iotsploit_protocols.canbus.errors import CanDefinitionError, CanValueError

pytestmark = pytest.mark.unit

POWERTRAIN = "bus_can_powertrain"


@pytest.fixture
def catalog(target):
    return TargetCanCatalog.from_target(target)


def frame(catalog, frame_id, is_extended=False):
    return catalog.resolve(POWERTRAIN, frame_id, is_extended=is_extended)


# ── known vectors ─────────────────────────────────────────────────────


def test_a_little_endian_frame_packs_to_known_bytes(catalog):
    """VehicleSpeed 42.5 is raw 425 (0x01A9) at bit 0, Intel order, so 0xA9
    then 0x01. IgnitionState 'On' is 2 at bit 16 and AliveCounter 3 sits above
    it at bit 18, giving 2 | (3 << 2) = 0x0E."""
    encoded = encode_frame(
        frame(catalog, 0x123),
        {"VehicleSpeed": "42.5", "IgnitionState": "On", "AliveCounter": "3"},
    )

    assert encoded.data_hex == "A9010E0000000000"
    assert encoded.dlc == 8
    assert encoded.is_extended is False
    assert encoded.is_fd is False


def test_a_motorola_signed_scaled_frame_packs_to_known_bytes(catalog):
    """BrakePressure -12.5 with factor 0.25 and offset -100 is raw 350
    (0x015E), big-endian from bit 7, so 0x01 then 0x5E. BrakeTemp -40 with
    offset -40 is raw 0."""
    encoded = encode_frame(
        frame(catalog, 0x2A1), {"BrakePressure": "-12.5", "BrakeTemp": "-40"}
    )

    assert encoded.data_hex == "015E000000000000"


# ── round trips ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "frame_id, is_extended, values",
    [
        (0x123, False, {"VehicleSpeed": "42.5", "IgnitionState": "On", "AliveCounter": "3"}),
        (0x123, True, {"ExtendedCounter": "65535"}),
        (0x2A1, False, {"BrakePressure": "-12.5", "BrakeTemp": "87"}),
        (0x300, False, {"Mode": "0", "SpeedA": "100.0", "Common": "7"}),
        (0x300, False, {"Mode": "1", "TempB": "-10", "Common": "255"}),
        (0x400, False, {"SerialNumber": "18446744073709551615", "BlockCounter": "1"}),
        (0x2B0, False, {"PackVoltage": "400.0", "PackMode": "Charging"}),
    ],
    ids=["classic", "extended", "motorola-signed", "mux-a", "mux-b", "fd-wide", "component"],
)
def test_every_fixture_survives_a_round_trip(catalog, frame_id, is_extended, values):
    """Encode then decode returns what was encoded, for every shape the plans
    care about. This is what proves bit placement rather than asserting it."""
    definition = frame(catalog, frame_id, is_extended)

    encoded = encode_frame(definition, values)
    decoded = decode_frame(definition, encoded.data)

    assert decoded.ok is True
    assert decoded.signals == encoded.signals


def test_a_wide_integer_supplied_as_text_is_not_rounded(catalog):
    """2**64-1 loses its last bits through a double. The editor sends numbers as
    text precisely so this parse happens in Python."""
    encoded = encode_frame(
        frame(catalog, 0x400),
        {"SerialNumber": "18446744073709551615", "BlockCounter": "0"},
    )

    assert encoded.signals["SerialNumber"] == 18446744073709551615
    assert encoded.data_hex.startswith("FFFFFFFFFFFFFFFF")


def test_an_fd_frame_keeps_its_flag_and_length(catalog):
    encoded = encode_frame(
        frame(catalog, 0x400), {"SerialNumber": "1", "BlockCounter": "2"}
    )

    assert encoded.is_fd is True
    assert encoded.dlc == 16


# ── choices ───────────────────────────────────────────────────────────


def test_a_label_and_its_number_encode_to_the_same_bytes(catalog):
    """An operator picking 'On' and an API sending 2 mean one frame."""
    definition = frame(catalog, 0x123)
    common = {"VehicleSpeed": "0", "AliveCounter": "0"}

    by_label = encode_frame(definition, {**common, "IgnitionState": "On"})
    by_number = encode_frame(definition, {**common, "IgnitionState": "2"})

    assert by_label.data == by_number.data


def test_an_unknown_label_lists_the_ones_that_exist(catalog):
    with pytest.raises(CanValueError) as caught:
        encode_frame(
            frame(catalog, 0x123),
            {"VehicleSpeed": "0", "IgnitionState": "Banana", "AliveCounter": "0"},
        )

    assert "Acc, Crank, Off, On" in caught.value.field_errors["signals.IgnitionState"]


def test_a_code_with_no_label_decodes_to_its_number_and_says_so(catalog):
    """The fixture labels 0..3 of a 2-bit field, so every code is labelled.
    Narrowing the table leaves a hole a real bus would also have."""
    definition = frame(catalog, 0x2B0)
    partial = definition.signal("PackMode")
    trimmed = definition.__class__(
        **{
            **definition.__dict__,
            "signals": tuple(
                s if s.name != "PackMode" else s.__class__(**{**s.__dict__, "choices": {0: "Idle"}})
                for s in definition.signals
            ),
        }
    )
    assert partial is not None

    encoded = encode_frame(trimmed, {"PackVoltage": "0", "PackMode": "2"})
    decoded = decode_frame(trimmed, encoded.data)

    assert decoded.ok is True
    assert decoded.signals["PackMode"] == 2
    assert "no label" in decoded.reason
    assert decoded.raw_values["PackMode"] == 2


# ── multiplexing ──────────────────────────────────────────────────────


def test_the_multiplexer_value_is_required_before_anything_else(catalog):
    """Which signals are even required depends on the answer, so this is the
    one error worth reporting on its own."""
    with pytest.raises(CanValueError) as caught:
        encode_frame(frame(catalog, 0x300), {"Common": "1", "SpeedA": "10"})

    assert caught.value.field_errors == {
        "signals.Mode": "the multiplexer value is required before the other signals are known"
    }


def test_a_value_from_an_unselected_branch_is_refused(catalog):
    """Silently dropping it would send a frame the operator did not compose."""
    with pytest.raises(CanValueError) as caught:
        encode_frame(
            frame(catalog, 0x300), {"Mode": "0", "SpeedA": "10", "TempB": "5", "Common": "1"}
        )

    assert "only present when Mode is 1" in caught.value.field_errors["signals.TempB"]


def test_decode_picks_the_branch_out_of_the_payload(catalog):
    """Never from a caller's claim about which branch it is: a decoder that
    takes that on trust reports one branch's names over another's bits."""
    definition = frame(catalog, 0x300)
    branch_b = encode_frame(definition, {"Mode": "1", "TempB": "-10", "Common": "9"})

    decoded = decode_frame(definition, branch_b.data)

    assert decoded.signals["TempB"] == -10
    assert "SpeedA" not in decoded.signals


# ── strictness of encoding ────────────────────────────────────────────


def test_a_missing_signal_is_named_rather_than_defaulted(catalog):
    """No zero fill. A frame sent with an unstated field silently filled in is
    not the frame the operator composed."""
    with pytest.raises(CanValueError) as caught:
        encode_frame(frame(catalog, 0x123), {"VehicleSpeed": "10"})

    assert caught.value.field_errors == {
        "signals.IgnitionState": "required",
        "signals.AliveCounter": "required",
    }


def test_a_misspelled_signal_name_fails(catalog):
    with pytest.raises(CanValueError) as caught:
        encode_frame(
            frame(catalog, 0x123),
            {
                "VehicleSpeed": "10",
                "IgnitionState": "Off",
                "AliveCounter": "1",
                "VehicleSpead": "10",
            },
        )

    assert "no signal by this name" in caught.value.field_errors["signals.VehicleSpead"]


def test_a_value_past_the_documented_maximum_fails(catalog):
    """cantools is the final validator, with the range the target stated."""
    with pytest.raises(CanValueError, match="could not be encoded"):
        encode_frame(
            frame(catalog, 0x123),
            {"VehicleSpeed": "300", "IgnitionState": "Off", "AliveCounter": "0"},
        )


@pytest.mark.parametrize("value", ["", "   ", None])
def test_an_empty_value_is_required_not_zero(catalog, value):
    with pytest.raises(CanValueError) as caught:
        encode_frame(
            frame(catalog, 0x123),
            {"VehicleSpeed": value, "IgnitionState": "Off", "AliveCounter": "0"},
        )

    assert caught.value.field_errors["signals.VehicleSpeed"] == "required"


def test_non_numeric_text_for_a_numeric_signal_fails(catalog):
    with pytest.raises(CanValueError) as caught:
        encode_frame(
            frame(catalog, 0x123),
            {"VehicleSpeed": "fast", "IgnitionState": "Off", "AliveCounter": "0"},
        )

    assert "not a number" in caught.value.field_errors["signals.VehicleSpeed"]


@pytest.mark.parametrize("boundary", ["-168", "87"])
def test_signed_boundaries_encode(catalog, boundary):
    """Off-by-one at a documented limit is where a sign error shows up."""
    encoded = encode_frame(
        frame(catalog, 0x2A1), {"BrakePressure": "0", "BrakeTemp": boundary}
    )

    assert decode_frame(frame(catalog, 0x2A1), encoded.data).signals["BrakeTemp"] == float(
        boundary
    )


# ── decoding never raises ─────────────────────────────────────────────


def test_a_short_payload_is_reported_not_padded(catalog):
    """A frame arriving shorter than its definition is a finding about the bus
    or the definition, and decoding the bytes present would hide it."""
    decoded = decode_frame(frame(catalog, 0x123), b"\x01\x02")

    assert decoded.ok is False
    assert "2 bytes" in decoded.reason and "8" in decoded.reason


def test_a_long_payload_is_reported_not_truncated(catalog):
    decoded = decode_frame(frame(catalog, 0x123), bytes(9))

    assert decoded.ok is False
    assert "9 bytes" in decoded.reason


def test_decoding_nothing_returns_a_failure(catalog):
    decoded = decode_frame(frame(catalog, 0x123), None)

    assert decoded.ok is False
    assert decoded.reason == "no payload to decode"


def test_decoding_a_container_frame_fails_without_raising(target):
    """The catalogue refuses this at resolve time, but a capture reaches the
    codec with whatever definition it holds and must not die on one."""
    catalog = TargetCanCatalog.from_target(target)
    container = catalog.bus(POWERTRAIN).frame(0x500, False)

    decoded = decode_frame(container, bytes(64))

    assert decoded.ok is False
    assert "container frame" in decoded.reason


# ── unbuildable definitions ───────────────────────────────────────────


def test_a_signal_reaching_past_the_payload_is_refused(target):
    """The catalogue's structural checks stop short of bit layout on purpose:
    cantools packs it, so cantools judges it."""
    target["buses"][0]["properties"]["messages"].append(
        {
            "frame_id": 0x704,
            "name": "Overhang",
            "dlc": 1,
            "signals": [
                {"name": "TooWide", "start_bit": 0, "length": 32, "byte_order": "little"}
            ],
        }
    )
    definition = TargetCanCatalog.from_target(target).resolve(POWERTRAIN, 0x704)

    with pytest.raises(CanDefinitionError, match="unusable layout"):
        build_message(definition)


# ── the cache ─────────────────────────────────────────────────────────


def test_the_codec_reuses_one_reconstruction_per_definition(catalog):
    """Rebuilding per frame at a few thousand frames a second is the difference
    between keeping up and dropping traffic."""
    codec = CanCodec()
    definition = frame(catalog, 0x123)

    first = codec.message(definition)
    second = codec.message(definition)

    assert first is second


def test_the_cache_is_keyed_on_content_not_identity(catalog):
    """Never on a target id: a target edited underneath the cache must not
    serve the layout it used to have."""
    codec = CanCodec()
    original = frame(catalog, 0x123)
    edited = original.__class__(**{**original.__dict__, "dlc": 7})

    assert codec.message(original) is not codec.message(edited)
