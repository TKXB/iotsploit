"""SocketCAN error frames must never be mistaken for traffic.

python-can strips CAN_ERR_FLAG before it exposes ``arbitration_id``, so a
controller fault arrives looking like an ordinary frame with id 0x004. A reader
that trusts that field reports a bus fault as an ECU message and invents a
frame nobody sent. These tests pin the classification that prevents it, using
the byte patterns a real bench Pi produced against a CAN FD bus.
"""

import pytest

from iotsploit_drivers.socketcan.can_errors import (
    CAN_ERR_BUSOFF,
    CAN_ERR_CRTL,
    CAN_ERR_LOSTARB,
    CAN_ERR_PROT,
    CAN_ERR_TRX,
    decode_error_frame,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("0004000000000000", "rx-error-warning"),
        ("0010000000000000", "rx-error-passive"),
        ("0008000000000000", "tx-error-warning"),
        ("0020000000000000", "tx-error-passive"),
        ("0040000000000000", "back-to-error-active"),
        ("0001000000000000", "rx-overflow"),
    ],
)
def test_controller_status_comes_from_data_byte_one(payload, expected):
    error = decode_error_frame(CAN_ERR_CRTL, bytes.fromhex(payload))

    assert error["classes"] == ["controller-problem"]
    assert error["controller"] == [expected]
    assert error["description"] == f"controller-problem{{{expected}}}"


def test_the_bench_capture_decodes_as_a_controller_fault():
    # Exactly what drv_socketcan used to log as "ID: 0x4, Data: 0004...".
    error = decode_error_frame(0x004, bytes.fromhex("0004000000000000"))

    assert error["description"] == "controller-problem{rx-error-warning}"
    assert error["error_class_id"] == 0x004
    assert error["data"] == "0004000000000000"


def test_several_classes_in_one_frame_are_all_reported():
    error = decode_error_frame(CAN_ERR_PROT | CAN_ERR_BUSOFF, bytes.fromhex("0000021800000000"))

    assert error["classes"] == ["protocol-violation", "bus-off"]
    assert error["protocol"] == ["form"]
    assert error["protocol_location"] == "crc-delimiter"
    assert error["description"] == "protocol-violation{form}@crc-delimiter bus-off"


def test_multiple_status_bits_in_one_byte_are_all_named():
    error = decode_error_frame(CAN_ERR_CRTL, bytes.fromhex("0014000000000000"))

    assert error["controller"] == ["rx-error-warning", "rx-error-passive"]


def test_transceiver_and_arbitration_read_their_own_bytes():
    error = decode_error_frame(CAN_ERR_TRX | CAN_ERR_LOSTARB, bytes.fromhex("0B00000004000000"))

    assert error["lost_arbitration_bit"] == 0x0B
    assert error["transceiver"] == "canh-no-wire"


def test_a_zero_status_byte_is_unspecified_not_a_flag_list():
    error = decode_error_frame(CAN_ERR_CRTL, bytes(8))

    assert error["controller"] == ["unspecified"]


def test_unknown_bits_are_surfaced_rather_than_dropped():
    error = decode_error_frame(0x800, bytes(8))

    assert error["classes"] == ["unknown(0x800)"]


@pytest.mark.parametrize("payload", [b"", b"\x00", None])
def test_a_short_frame_does_not_raise(payload):
    # An acquisition loop must survive a truncated error frame.
    error = decode_error_frame(CAN_ERR_CRTL, payload)

    assert error["classes"] == ["controller-problem"]
    assert "controller" not in error
