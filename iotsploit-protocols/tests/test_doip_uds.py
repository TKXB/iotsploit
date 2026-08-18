"""UDS semantics, against a scripted transport.

No sockets here: UDS is deliberately independent of how bytes travel, so a fake
transport is the honest test. What is being pinned is the parsing the old code
did with magic offsets, and the responsePending handling it had commented out.
"""

from __future__ import annotations

import pytest

from iotsploit_protocols.doip.uds import (
    NRC_RESPONSE_PENDING,
    SESSION_PROGRAMMING,
    UdsClient,
    UdsResponse,
)
from iotsploit_protocols.errors import ProtocolError

pytestmark = pytest.mark.unit


class FakeTransport:
    """Returns scripted responses; records what it was asked and how."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []
        self.reads = 0

    def request(self, payload: bytes) -> bytes:
        self.sent.append(payload)
        return self._next()

    def read(self) -> bytes:
        self.reads += 1
        return self._next()

    def _next(self) -> bytes:
        if not self.responses:
            raise AssertionError("transport asked for more responses than scripted")
        return self.responses.pop(0)


def negative(service: int, nrc: int) -> bytes:
    return bytes([0x7F, service, nrc])


# ── parsing ───────────────────────────────────────────────────────────────


def test_a_positive_response_carries_its_data():
    uds = UdsClient(FakeTransport(b"\x62\xf1\x90ABC"))

    response = uds.read_did(0xF190)

    assert response.ok
    assert response.data == b"\xf1\x90ABC"


def test_a_negative_response_is_not_an_exception():
    """'The ECU said no' is frequently the finding, so it is a value not a raise."""
    uds = UdsClient(FakeTransport(negative(0x22, 0x33)))

    response = uds.read_did(0xF190)

    assert not response.ok
    assert response.nrc == 0x33


def test_the_nrc_gets_its_standard_name():
    """resp_buf[-3] told you nothing; a name tells you what to do."""
    uds = UdsClient(FakeTransport(negative(0x27, 0x35)))

    response = uds.request(b"\x27\x01")

    assert "invalidKey" in response.nrc_name


def test_a_response_for_another_service_is_rejected():
    """Right shape, wrong service: never hand that back as the answer."""
    uds = UdsClient(FakeTransport(b"\x62\xf1\x90"))

    with pytest.raises(ProtocolError, match="expected 0x50"):
        uds.session()


def test_a_negative_response_echoing_another_service_is_rejected():
    uds = UdsClient(FakeTransport(negative(0x22, 0x33)))

    with pytest.raises(ProtocolError, match="echoes service"):
        uds.session()


def test_an_empty_response_is_an_error():
    uds = UdsClient(FakeTransport(b""))

    with pytest.raises(ProtocolError, match="empty response"):
        uds.session()


def test_a_truncated_negative_response_is_an_error():
    uds = UdsClient(FakeTransport(b"\x7f\x10"))

    with pytest.raises(ProtocolError, match="truncated"):
        uds.session()


# ── response pending ──────────────────────────────────────────────────────


def test_a_pending_response_is_waited_through():
    """The old code had this commented out, so a busy ECU read as a failure."""
    transport = FakeTransport(negative(0x31, NRC_RESPONSE_PENDING), b"\x71\x01\x02\x32")
    uds = UdsClient(transport)

    response = uds.routine(0x01, 0x0232)

    assert response.ok
    assert response.data == b"\x01\x02\x32"


def test_waiting_reads_rather_than_resending():
    """Re-sending a routine request does not retry it -- it performs it twice."""
    transport = FakeTransport(negative(0x31, NRC_RESPONSE_PENDING), b"\x71\x01\x02\x32")
    uds = UdsClient(transport)

    uds.routine(0x01, 0x0232)

    assert len(transport.sent) == 1
    assert transport.reads == 1


def test_several_pending_responses_are_tolerated():
    pending = negative(0x31, NRC_RESPONSE_PENDING)
    transport = FakeTransport(pending, pending, pending, b"\x71\x01\x02\x32")

    assert UdsClient(transport).routine(0x01, 0x0232).ok


def test_endless_pending_gives_up_rather_than_hanging():
    pending = negative(0x31, NRC_RESPONSE_PENDING)
    transport = FakeTransport(*[pending] * 10)
    uds = UdsClient(transport, response_pending_attempts=3)

    with pytest.raises(ProtocolError, match="stayed pending"):
        uds.routine(0x01, 0x0232)


# ── services ──────────────────────────────────────────────────────────────


def test_session_control_sends_the_requested_session():
    transport = FakeTransport(b"\x50\x02")
    UdsClient(transport).session(SESSION_PROGRAMMING)

    assert transport.sent == [b"\x10\x02"]


def test_read_did_encodes_the_identifier():
    transport = FakeTransport(b"\x62\xf1\x90")
    UdsClient(transport).read_did(0xF190)

    assert transport.sent == [b"\x22\xf1\x90"]


def test_routine_encodes_control_and_id():
    transport = FakeTransport(b"\x71\x01\x02\x32")
    UdsClient(transport).routine(0x01, 0x0232)

    assert transport.sent == [b"\x31\x01\x02\x32"]


def test_is_alive_accepts_a_negative_response():
    """A refusal still proves something is there speaking UDS."""
    assert UdsClient(FakeTransport(negative(0x10, 0x22))).is_alive()


def test_is_alive_is_false_when_nothing_answers():
    class Dead:
        def request(self, payload):
            raise TimeoutError("no answer")

        def read(self):
            raise TimeoutError("no answer")

    assert not UdsClient(Dead()).is_alive()


def test_an_empty_payload_is_refused():
    with pytest.raises(ValueError, match="must not be empty"):
        UdsClient(FakeTransport()).request(b"")


# ── security access ───────────────────────────────────────────────────────


def test_security_access_derives_the_key_from_the_seed():
    transport = FakeTransport(b"\x67\x19\xAA\xBB\xCC", b"\x67\x1a")
    seen = {}

    def key_fn(seed, pin):
        seen["seed"], seen["pin"] = seed, pin
        return b"\x11\x22\x33"

    assert UdsClient(transport).security_access(0x19, b"PIN45", key_fn)
    # 0x19 is the echoed sub-function, not seed material. Passing it to the
    # derivation yields a key the ECU rejects, which reads as a wrong PIN.
    assert seen["seed"] == b"\xAA\xBB\xCC"
    assert transport.sent[1] == b"\x27\x1a\x11\x22\x33"


def test_the_send_key_subfunction_is_one_above_request_seed():
    transport = FakeTransport(b"\x67\x01\xAA\xBB", b"\x67\x02")
    UdsClient(transport).security_access(0x01, b"PIN45", lambda s, p: b"\x00")

    assert transport.sent[0][1] == 0x01
    assert transport.sent[1][1] == 0x02


def test_a_refused_seed_is_a_failure_not_a_crash():
    transport = FakeTransport(negative(0x27, 0x22))

    assert not UdsClient(transport).security_access(0x19, b"PIN45", lambda s, p: b"")


def test_a_rejected_key_is_a_failure():
    transport = FakeTransport(b"\x67\x19\xAA\xBB", negative(0x27, 0x35))

    assert not UdsClient(transport).security_access(0x19, b"PIN45", lambda s, p: b"\x00")


def test_an_all_zero_seed_means_already_unlocked():
    """Deriving a key from a zero seed and sending it would fail a fine state."""
    transport = FakeTransport(b"\x67\x19\x00\x00\x00")
    called = []
    # data is 19 00 00 00: the echo is stripped, leaving an all-zero seed.

    assert UdsClient(transport).security_access(
        0x19, b"PIN45", lambda s, p: called.append(1) or b""
    )
    assert called == []


def test_an_empty_seed_is_a_protocol_error():
    transport = FakeTransport(b"\x67\x19")

    with pytest.raises(ProtocolError, match="empty seed"):
        UdsClient(transport).security_access(0x19, b"PIN45", lambda s, p: b"")


def test_the_algorithm_is_passed_in_not_looked_up():
    """The derivation is proprietary; a registry of them would ship them."""
    import inspect

    signature = inspect.signature(UdsClient.security_access)

    assert "key_fn" in signature.parameters
    assert not hasattr(UdsClient, "seed_key_algorithms")


# ── the response object ───────────────────────────────────────────────────


def test_a_positive_response_has_no_nrc_name():
    assert UdsResponse(service=0x10, data=b"\x01").nrc_name == ""
