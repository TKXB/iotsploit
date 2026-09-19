"""Reading a Vector ASC log back as frames.

Every case here is one where a wrong parse produces plausible numbers rather
than an error, which is what makes them worth pinning:

* the ``base`` directive reaching columns it does not govern truncates the
  largest payloads in the file and nothing else;
* a CAN FD length code read as a byte count silently shortens every frame over
  eight bytes;
* the other CAN FD column order parses far enough to yield a frame whose
  identifier is really its direction.

The multi-byte payload assertions are hand-checkable on purpose: a length that
agrees with a wrong offset is exactly the failure a length-only assertion
misses.
"""

from __future__ import annotations

import can
import pytest
from can.io import BLFWriter, CanutilsLogWriter, TRCWriter

from iotsploit_protocols.canbus.logfile import (
    CanLogError,
    identities_from_log,
    normalize_log_channel,
    open_log,
    select_log_channel,
)

pytestmark = pytest.mark.unit


def write(tmp_path, body, name="capture.asc"):
    path = tmp_path / name
    path.write_text(body)
    return path


def read(tmp_path, body, **kwargs):
    reader = open_log(write(tmp_path, body), **kwargs)
    return list(reader.messages()), reader.stats


# ── the column order in the sample file ───────────────────────────────

IDENTIFIER_FIRST = """date Tue Sep 15 01:30:06 PM 2026
base hex  timestamps absolute
// version 7.0.0
0.000000 CANFD 2 194 Rx 1 0 d 8 8 f3 03 10 00 00 00 00 00
0.020700 CANFD 2 15a Rx 1 0 d 10 16 c5 08 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0.020900 CANFD 2 120 Rx 1 0 d 12 24 d2 25 48 48 48 48 48 48 40 08 48 48 48 08 48 48 20 00 00 00 00 00 00 00
End Triggerblock
"""


def test_the_sample_column_order_reads_identifier_direction_and_payload(tmp_path):
    messages, stats = read(tmp_path, IDENTIFIER_FIRST)

    assert stats.unparsable_lines == 0
    assert [message.arbitration_id for message in messages] == [0x194, 0x15A, 0x120]
    assert messages[0].data == b"\xf3\x03\x10\x00\x00\x00\x00\x00"
    assert messages[0].is_fd is True
    assert messages[0].channel == 2


@pytest.mark.parametrize(
    "index, dlc, expected_length",
    [(0, 8, 8), (1, 10, 16), (2, 12, 24)],
    ids=["dlc-8-is-8-bytes", "dlc-10-is-16-bytes", "dlc-12-is-24-bytes"],
)
def test_a_length_code_is_expanded_to_its_byte_count(tmp_path, index, dlc, expected_length):
    """CAN FD's DLC indexes a table above eight. Reading the code as a count
    would cut the 16-byte frame to 10 bytes and the 24-byte frame to 12."""
    messages, _ = read(tmp_path, IDENTIFIER_FIRST)

    assert len(messages[index].data) == expected_length


def test_a_number_too_long_to_parse_counts_as_unparsable(tmp_path):
    """Found by fuzzing. ``int()`` refuses a string of more than 4300 digits,
    and this reader's contract is that a line it cannot parse is counted and
    skipped -- never guessed at and never fatal."""
    frames, stats = read(tmp_path, f"   0.100000 1  123             Rx   d {'9' * 6000} AA BB\n")

    assert frames == []
    assert stats.unparsable_lines == 1


def test_the_last_payload_byte_is_the_one_the_line_ends_with(tmp_path):
    """A payload read at the wrong offset can still have the right length.
    Anchoring on the final byte is what catches that."""
    messages, _ = read(tmp_path, IDENTIFIER_FIRST)

    assert messages[2].data[:2] == b"\xd2\x25"
    assert messages[2].data[-1:] == b"\x00"
    assert messages[1].data[:2] == b"\xc5\x08"


# ── Vector's own column order ─────────────────────────────────────────


def test_the_direction_first_column_order_reads_the_same_frame(tmp_path):
    """Vector writes ``channel direction identifier``; the sample file writes
    ``channel identifier direction``. Both are real, so both must land."""
    messages, stats = read(
        tmp_path,
        "base hex timestamps absolute\n"
        "0.006443 CANFD 1 Rx 11a BrakeStatus 0 0 8 8 01 02 03 04 05 06 07 08 106000 0 0 0 0\n",
    )

    assert stats.unparsable_lines == 0
    assert messages[0].arbitration_id == 0x11A
    assert messages[0].data == bytes(range(1, 9))


def test_a_classic_line_carries_its_dlc_as_a_byte_count(tmp_path):
    messages, stats = read(
        tmp_path, "base hex timestamps absolute\n0.011165 1 100 Rx d 8 11 22 33 44 55 66 77 88\n"
    )

    assert stats.unparsable_lines == 0
    assert messages[0].arbitration_id == 0x100
    assert messages[0].data.hex() == "1122334455667788"
    assert messages[0].is_fd is False


# ── the directives, and what they do and do not govern ────────────────


def test_a_decimal_base_reads_identifiers_as_decimal(tmp_path):
    messages, _ = read(
        tmp_path, "base dec timestamps absolute\n0.000000 1 291 Rx d 1 ff\n"
    )

    assert messages[0].arbitration_id == 291


def test_the_base_directive_never_reaches_the_length_columns(tmp_path):
    """``base hex`` governs identifiers only. Reading ``10 16`` as hex yields a
    22-byte read of a 16-byte frame, which is the whole bug this pins."""
    messages, stats = read(
        tmp_path,
        "base hex timestamps absolute\n"
        "0.0 CANFD 2 15a Rx 1 0 d 10 16 c5 08 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n",
    )

    assert stats.unparsable_lines == 0
    assert len(messages[0].data) == 16


def test_relative_timestamps_are_anchored_to_the_logs_own_date(tmp_path):
    """Without the date header every arrival time in a replay renders as 1970."""
    _, stats = read(tmp_path, IDENTIFIER_FIRST)

    assert stats.started_at is not None
    assert (stats.started_at.year, stats.started_at.month, stats.started_at.day) == (2026, 9, 15)
    assert (stats.started_at.hour, stats.started_at.minute) == (13, 30)


def test_an_extended_identifier_keeps_its_width(tmp_path):
    messages, _ = read(
        tmp_path, "base hex timestamps absolute\n0.0 1 18DB33F1x Rx d 1 aa\n"
    )

    assert messages[0].arbitration_id == 0x18DB33F1
    assert messages[0].is_extended_id is True


# ── what is not traffic ───────────────────────────────────────────────


def test_an_error_frame_is_flagged_rather_than_given_an_identifier(tmp_path):
    """The aggregator tallies faults separately and only looks at this flag.
    A fault that arrived here as a frame would become a row no ECU ever sent."""
    messages, stats = read(
        tmp_path, "base hex timestamps absolute\n0.5 1 ErrorFrame ECC: 10100010\n"
    )

    assert messages[0].is_error_frame is True
    assert stats.error_frames == 1
    assert stats.frames == 0


def test_a_remote_frame_carries_no_payload(tmp_path):
    messages, _ = read(tmp_path, "base hex timestamps absolute\n0.0 1 200 Rx r 8\n")

    assert messages[0].is_remote_frame is True
    assert messages[0].data == b""


def test_a_transmit_request_is_not_replayed_alongside_its_transmission(tmp_path):
    """TxRq is logged in addition to the Tx that follows, so replaying both
    would count every frame this host sent twice."""
    messages, stats = read(
        tmp_path,
        "base hex timestamps absolute\n"
        "0.0 1 100 TxRq d 1 aa\n"
        "0.1 1 100 Tx d 1 aa\n",
    )

    assert len(messages) == 1
    assert stats.unparsable_lines == 0


# ── partial reads, and saying so ──────────────────────────────────────


def test_a_corrupt_line_is_counted_and_the_rest_of_the_log_still_reads(tmp_path):
    """One bad line in fifty thousand must not end a replay."""
    messages, stats = read(
        tmp_path,
        "base hex timestamps absolute\n"
        "0.0 1 100 Rx d 8 11 22 33 44 55 66 77 88\n"
        "0.1 1 101 Rx d 8 11 22\n"
        "0.2 1 102 Rx d 1 ff\n",
    )

    assert [message.arbitration_id for message in messages] == [0x100, 0x102]
    assert stats.unparsable_lines == 1


def test_a_disagreeing_dlc_and_length_is_refused_rather_than_read(tmp_path):
    """Both columns describe the same payload. When they disagree the offset is
    wrong, and the bytes that follow are not the ones the line describes."""
    _, stats = read(
        tmp_path, "base hex timestamps absolute\n0.0 CANFD 2 15a Rx 1 0 d 10 24 c5 08\n"
    )

    assert stats.unparsable_lines == 1
    assert stats.frames == 0


def test_a_frame_budget_stops_the_read_and_marks_it_truncated(tmp_path):
    messages, stats = read(tmp_path, IDENTIFIER_FIRST, max_frames=2)

    assert len(messages) == 2
    assert stats.truncated is True


# ── channels ──────────────────────────────────────────────────────────


TWO_CHANNELS = """base hex timestamps absolute
0.0 1 100 Rx d 1 11
0.1 2 200 Rx d 1 22
0.2 1 101 Rx d 1 33
"""


def test_every_channel_in_the_log_is_reported(tmp_path):
    _, stats = read(tmp_path, TWO_CHANNELS)

    assert stats.channels_present == {1, 2}


def test_selecting_a_channel_replays_only_that_bus(tmp_path):
    """A multi-channel log holds several buses. Decoding all of them against
    one target bus is how a replay produces values that look right."""
    messages, stats = read(tmp_path, TWO_CHANNELS, channel=1)

    assert [message.arbitration_id for message in messages] == [0x100, 0x101]
    assert stats.frames == 2
    assert stats.channels_present == {1, 2}


# ── choosing a reader ─────────────────────────────────────────────────


def test_an_unsupported_format_is_named_rather_than_parsed_as_asc(tmp_path):
    path = write(tmp_path, "", name="capture.pcap")

    with pytest.raises(CanLogError, match="not a CAN log this can replay"):
        open_log(path)


@pytest.mark.parametrize(
    ("writer_type", "name", "expected_format", "expected_channel"),
    [
        (BLFWriter, "capture.blf", "blf", 1),
        (CanutilsLogWriter, "capture.log", "candump", "can0"),
        (TRCWriter, "capture.trc", "trc", 1),
    ],
)
def test_python_can_formats_preserve_frame_fields(
    tmp_path, writer_type, name, expected_format, expected_channel
):
    path = tmp_path / name
    message = can.Message(
        timestamp=1_700_000_000.25,
        arbitration_id=0x18DB33F1,
        data=b"\x01\x02\x03",
        is_extended_id=True,
        channel=0,
    )
    with writer_type(path) as writer:
        writer.on_message_received(message)

    reader = open_log(path)
    messages = list(reader.messages())

    assert reader.stats.format == expected_format
    assert reader.stats.channels_present == {expected_channel}
    assert messages[0].arbitration_id == 0x18DB33F1
    assert messages[0].data == b"\x01\x02\x03"
    assert messages[0].is_extended_id is True
    assert messages[0].channel == expected_channel


def test_candump_named_channel_can_be_selected(tmp_path):
    path = tmp_path / "capture.log"
    with CanutilsLogWriter(path) as writer:
        for channel, frame_id in (("can0", 0x100), ("vcan1", 0x200)):
            writer.on_message_received(
                can.Message(
                    timestamp=1_700_000_000,
                    arbitration_id=frame_id,
                    data=b"\x01",
                    channel=channel,
                )
            )

    reader = open_log(path, channel="vcan1")

    assert [message.arbitration_id for message in reader.messages()] == [0x200]
    assert reader.stats.channels_present == {"can0", "vcan1"}


def test_channel_selection_requires_an_explicit_choice_for_a_multi_bus_log():
    with pytest.raises(CanLogError, match="multiple channels"):
        select_log_channel({1, 2}, None)

    assert select_log_channel({"can0"}, None) == "can0"
    assert normalize_log_channel(" 2 ") == 2
    assert normalize_log_channel(" vcan0 ") == "vcan0"


def test_invalid_content_for_a_supported_suffix_is_reported(tmp_path):
    reader = open_log(write(tmp_path, "not a blf", name="capture.blf"))

    with pytest.raises(CanLogError, match="cannot parse BLF"):
        list(reader.messages())


def test_trc_3_is_rejected_before_can_xl_can_be_partially_replayed(tmp_path):
    reader = open_log(
        write(
            tmp_path,
            ";$FILEVERSION=3.0\n;$STARTTIME=45244.0\n1 0.0 DT 1 123 Rx 1 01\n",
            name="capture.trc",
        )
    )

    with pytest.raises(CanLogError, match="TRC 3/CAN XL is not supported"):
        list(reader.messages())


def test_a_missing_log_says_which_host_the_path_is_read_on(tmp_path):
    with pytest.raises(CanLogError, match="not necessarily the host running the UI"):
        open_log(tmp_path / "absent.asc")


def test_identities_exclude_faults_and_remote_requests(tmp_path):
    """What the bus scorer is given has to be traffic and nothing else."""
    path = write(
        tmp_path,
        "base hex timestamps absolute\n"
        "0.0 1 100 Rx d 1 11\n"
        "0.1 1 ErrorFrame\n"
        "0.2 1 200 Rx r 8\n"
        "0.3 1 18DB33F1x Rx d 1 22\n",
    )

    assert identities_from_log(path) == {(0x100, False), (0x18DB33F1, True)}
