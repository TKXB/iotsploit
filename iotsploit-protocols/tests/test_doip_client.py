"""The DoIP client, against a gateway on loopback.

Every test here corresponds to something the code this replaces got wrong.
The framing cases in particular: the old client read a fixed 13 bytes, slept
half a second and read again, which works only when the network happens to
deliver one message per segment.
"""

from __future__ import annotations

import socket
import threading

import pytest

from iotsploit_protocols.doip import DoipClient, DoipConfig, RoutingActivationFailed
from iotsploit_protocols.doip.client import (
    PT_ALIVE_CHECK_REQUEST,
    PT_DIAGNOSTIC_ACK,
    PT_DIAGNOSTIC_MESSAGE,
    PT_DIAGNOSTIC_NACK,
    PT_GENERIC_NACK,
    PT_ROUTING_ACTIVATION_RESPONSE,
)
from iotsploit_protocols.errors import NotConfigured, ProtocolError

pytestmark = pytest.mark.unit

TESTER = 0x0E80
ECU = 0x1011


def message(payload_type: int, body: bytes) -> bytes:
    """One DoIP message, built by hand so the test does not lean on the client."""
    return b"\x02\xfd" + payload_type.to_bytes(2, "big") + len(body).to_bytes(4, "big") + body


def activation(code: int = 0x10) -> bytes:
    return message(
        PT_ROUTING_ACTIVATION_RESPONSE,
        TESTER.to_bytes(2, "big") + ECU.to_bytes(2, "big") + bytes([code]) + b"\x00\x00\x00\x00",
    )


def diagnostic(payload: bytes) -> bytes:
    return message(PT_DIAGNOSTIC_MESSAGE, ECU.to_bytes(2, "big") + TESTER.to_bytes(2, "big") + payload)


def ack() -> bytes:
    return message(PT_DIAGNOSTIC_ACK, ECU.to_bytes(2, "big") + TESTER.to_bytes(2, "big") + b"\x00")


class Gateway:
    """A DoIP entity that replies with a scripted sequence per request."""

    def __init__(self, script, activation_reply=None, hangup=False):
        self.script = list(script)
        # Close after the script instead of idling: a peer that dies mid-message
        # and a peer that simply goes quiet are different failures.
        self.hangup = hangup
        self.activation_reply = activation_reply if activation_reply is not None else activation()
        self.requests = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
            with conn:
                first = conn.recv(4096)          # routing activation
                self.requests.append(first)
                if self.activation_reply:
                    conn.sendall(self.activation_reply)
                for step in self.script:
                    data = conn.recv(4096)       # a diagnostic request
                    if not data:
                        return
                    self.requests.append(data)
                    for chunk in step:
                        conn.sendall(chunk)
                if self.hangup:
                    return
                # Stay open so "silent" and "hung up" remain distinguishable.
                conn.recv(4096)
        except OSError:
            pass

    def close(self):
        self.sock.close()


@pytest.fixture
def gateway():
    servers = []

    def start(script=(), activation_reply=None, hangup=False):
        server = Gateway(script, activation_reply, hangup)
        servers.append(server)
        config = DoipConfig(
            host="127.0.0.1", port=server.port, logical_address=ECU,
            tester_address=TESTER, timeout=3.0,
        )
        return server, config

    yield start
    for server in servers:
        server.close()


# ── routing activation ────────────────────────────────────────────────────


def test_routing_activation_happens_on_connect(gateway):
    server, config = gateway(script=[[diagnostic(b"\x50\x01")]])

    with DoipClient(config) as client:
        client.request(b"\x10\x01")

    activation_request = server.requests[0]
    assert activation_request[2:4] == b"\x00\x05"          # payload type
    assert activation_request[8:10] == TESTER.to_bytes(2, "big")


def test_a_refused_activation_fails_loudly(gateway):
    """The old client pressed on regardless, so a refusal looked like a silent ECU."""
    _, config = gateway(activation_reply=activation(code=0x06))

    with pytest.raises(RoutingActivationFailed, match="unsupported activation type"):
        DoipClient(config).connect()


def test_a_refused_activation_leaves_no_open_socket(gateway):
    _, config = gateway(activation_reply=activation(code=0x02))
    client = DoipClient(config)

    with pytest.raises(RoutingActivationFailed):
        client.connect()

    assert not client.connected


# ── framing ───────────────────────────────────────────────────────────────


def test_a_response_split_across_segments_is_reassembled(gateway):
    """The bug in the old client: one recv is not one message."""
    whole = diagnostic(b"\x62\xf1\x90ABCDEFGH")
    _, config = gateway(script=[[whole[:3], whole[3:9], whole[9:]]])

    with DoipClient(config) as client:
        assert client.request(b"\x22\xf1\x90") == b"\x62\xf1\x90ABCDEFGH"


def test_an_ack_coalesced_with_the_response_does_not_swallow_it(gateway):
    """The old client read a fixed 13 bytes for the ack and lost whatever followed."""
    _, config = gateway(script=[[ack() + diagnostic(b"\x50\x03")]])

    with DoipClient(config) as client:
        assert client.request(b"\x10\x03") == b"\x50\x03"


def test_the_diagnostic_ack_is_consumed_not_returned(gateway):
    """It says the gateway took the message, which is not an answer."""
    _, config = gateway(script=[[ack(), diagnostic(b"\x50\x01")]])

    with DoipClient(config) as client:
        assert client.request(b"\x10\x01") == b"\x50\x01"


def test_an_implausible_length_is_rejected(gateway):
    """A desynchronized stream must fail, not try to read 4GB."""
    _, config = gateway(script=[[b"\x02\xfd\x80\x01\xff\xff\xff\xff"]])

    with DoipClient(config) as client:
        with pytest.raises(ProtocolError, match="implausible"):
            client.request(b"\x10\x01")


# ── protocol errors ───────────────────────────────────────────────────────


def test_a_diagnostic_nack_is_an_error(gateway):
    body = ECU.to_bytes(2, "big") + TESTER.to_bytes(2, "big") + b"\x03"
    _, config = gateway(script=[[message(PT_DIAGNOSTIC_NACK, body)]])

    with DoipClient(config) as client:
        with pytest.raises(ProtocolError, match="refused the diagnostic message"):
            client.request(b"\x10\x01")


def test_a_generic_header_nack_is_an_error(gateway):
    _, config = gateway(script=[[message(PT_GENERIC_NACK, b"\x02")]])

    with DoipClient(config) as client:
        with pytest.raises(ProtocolError, match="negative acknowledge"):
            client.request(b"\x10\x01")


def test_an_alive_check_is_answered_and_the_exchange_continues(gateway):
    """Ignoring it, as the old client did, gets the connection dropped mid-session."""
    alive = message(PT_ALIVE_CHECK_REQUEST, b"")
    server, config = gateway(script=[[alive, diagnostic(b"\x50\x01")]])

    with DoipClient(config) as client:
        assert client.request(b"\x10\x01") == b"\x50\x01"


def test_a_peer_that_hangs_up_mid_message_is_an_error(gateway):
    _, config = gateway(script=[[diagnostic(b"\x62\xf1\x90AAAA")[:9]]], hangup=True)

    with DoipClient(config) as client:
        with pytest.raises(ProtocolError, match="closed after"):
            client.request(b"\x22\xf1\x90")


def test_using_the_client_unconnected_is_an_error():
    client = DoipClient(DoipConfig(host="127.0.0.1", logical_address=ECU))

    with pytest.raises(ProtocolError, match="not connected"):
        client.request(b"\x10\x01")


# ── addressing ────────────────────────────────────────────────────────────


def test_the_request_carries_the_configured_addresses(gateway):
    """The old client hardcoded 0x0e80 even though the facet had the field."""
    server, config = gateway(script=[[diagnostic(b"\x50\x01")]])

    with DoipClient(config) as client:
        client.request(b"\x10\x01")

    body = server.requests[1][8:]
    assert body[0:2] == TESTER.to_bytes(2, "big")
    assert body[2:4] == ECU.to_bytes(2, "big")
    assert body[4:] == b"\x10\x01"


# ── configuration ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"host": "", "logical_address": ECU}, "host is required"),
        ({"host": "127.0.0.1", "logical_address": ECU, "port": 0}, "out of range"),
        ({"host": "127.0.0.1", "logical_address": 0x1FFFF}, "16-bit"),
        ({"host": "127.0.0.1", "logical_address": ECU, "tester_address": -1}, "16-bit"),
    ],
)
def test_an_unusable_config_fails_at_construction(kwargs, match):
    with pytest.raises(NotConfigured, match=match):
        DoipConfig(**kwargs)


def test_the_port_defaults_to_the_standard_one():
    """13400 is an IANA registration, not a description of one vehicle."""
    assert DoipConfig(host="127.0.0.1", logical_address=ECU).port == 13400
