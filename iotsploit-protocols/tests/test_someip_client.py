"""The SOME/IP client, against a server on loopback.

No hardware and no network: a thread on 127.0.0.1 plays the ECU. What is worth
testing here is not "can scapy encode a header" -- that would test scapy -- but
the things this module actually owns: framing over a stream, matching a reply to
its request, and refusing to treat a well-formed refusal as success.
"""

from __future__ import annotations

import socket
import threading

import pytest

from iotsploit_protocols.errors import NotConfigured, ProtocolError
from iotsploit_protocols.someip import SomeIpClient, SomeIpConfig
from iotsploit_protocols.someip.client import TYPE_ERROR, TYPE_RESPONSE
from iotsploit_protocols.someip.codec import application_payload

pytestmark = pytest.mark.unit


def reply(service, method, client_id, session_id, payload=b"", message_type=TYPE_RESPONSE, retcode=0):
    """One SOME/IP message, built by hand so the test does not lean on the client."""
    body = (
        client_id.to_bytes(2, "big")
        + session_id.to_bytes(2, "big")
        + b"\x01\x01"
        + bytes([message_type, retcode])
        + payload
    )
    return (
        service.to_bytes(2, "big")
        + method.to_bytes(2, "big")
        + len(body).to_bytes(4, "big")
        + body
    )


class Server:
    """A one-connection TCP or UDP peer that answers with canned bytes."""

    def __init__(self, responder, transport="tcp", hangup=False):
        self.responder = responder
        self.transport = transport
        # Close the connection after answering once, to model a peer that dies
        # mid-message. Distinct from a peer that simply stays quiet.
        self.hangup = hangup
        kind = socket.SOCK_STREAM if transport == "tcp" else socket.SOCK_DGRAM
        self.sock = socket.socket(socket.AF_INET, kind)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        if transport == "tcp":
            self.sock.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        # Serves requests until the client goes away. A responder that yields
        # nothing leaves the connection open on purpose: "peer says nothing" and
        # "peer hangs up" are different failures and the timeout test needs the
        # first one.
        try:
            if self.transport == "tcp":
                conn, _ = self.sock.accept()
                with conn:
                    while True:
                        request = conn.recv(4096)
                        if not request:
                            return
                        for chunk in self.responder(request):
                            conn.sendall(chunk)
                        if self.hangup:
                            return
            else:
                while True:
                    request, peer = self.sock.recvfrom(65535)
                    for chunk in self.responder(request):
                        self.sock.sendto(chunk, peer)
        except OSError:
            pass

    def close(self):
        self.sock.close()


@pytest.fixture
def serve():
    servers = []

    def start(responder, transport="tcp", hangup=False):
        server = Server(responder, transport, hangup)
        servers.append(server)
        return SomeIpConfig(host="127.0.0.1", port=server.port, transport=transport, timeout=3.0)

    yield start
    for server in servers:
        server.close()


def session_of(request):
    return int.from_bytes(request[10:12], "big")


def test_a_positive_response_carries_its_payload(serve):
    config = serve(lambda req: [reply(0x1234, 0x0002, 0xBEEF, session_of(req), b"\xAA\xBB")])
    with SomeIpClient(SomeIpConfig(**{**config.__dict__, "client_id": 0xBEEF})) as client:
        response = client.call(service=0x1234, instance=1, method=0x0002)

    assert response.ok
    assert response.payload == b"\xAA\xBB"


def test_scapy_27_data_field_carries_the_application_payload():
    class Packet:
        data = [b"\xAA", b"\xBB"]
        payload = b""

    assert application_payload(Packet()) == b"\xAA\xBB"


def test_scapy_26_packet_payload_still_works():
    class Packet:
        data = None
        payload = b"\xCC\xDD"

    assert application_payload(Packet()) == b"\xCC\xDD"


def test_an_error_reply_is_not_success(serve):
    """E_UNKNOWN_METHOD is a well-formed answer meaning no. Bytes came back; it still failed."""
    config = serve(
        lambda req: [
            reply(0x1234, 0x0009, 0x0001, session_of(req), message_type=TYPE_ERROR, retcode=0x03)
        ]
    )
    with SomeIpClient(config) as client:
        response = client.call(service=0x1234, instance=1, method=0x0009)

    assert not response.ok
    assert response.return_code_name == "E_UNKNOWN_METHOD"


def test_a_response_split_across_tcp_segments_is_reassembled(serve):
    """The bug the old DoIP code had: one recv is not one message."""
    def responder(req):
        whole = reply(0x1234, 0x0002, 0x0001, session_of(req), b"\x01\x02\x03\x04")
        return [whole[:5], whole[5:11], whole[11:]]

    config = serve(responder)
    with SomeIpClient(config) as client:
        response = client.call(service=0x1234, instance=1, method=0x0002)

    assert response.ok
    assert response.payload == b"\x01\x02\x03\x04"


def test_two_responses_in_one_segment_do_not_merge(serve):
    """Coalesced messages must not become one packet with a doubled payload."""
    def responder(req):
        session = session_of(req)
        stale = reply(0x1234, 0x0002, 0x0001, (session + 500) % 0xFFFF, b"\xFF\xFF")
        wanted = reply(0x1234, 0x0002, 0x0001, session, b"\x42")
        return [stale + wanted]

    config = serve(responder)
    with SomeIpClient(config) as client:
        response = client.call(service=0x1234, instance=1, method=0x0002)

    assert response.payload == b"\x42"


def test_an_interleaved_message_for_another_session_is_skipped(serve):
    """Over UDP an event can land between a request and its answer."""
    def responder(req):
        session = session_of(req)
        return [
            reply(0x9999, 0x8001, 0x0001, (session + 7) % 0xFFFF, b"\xDE\xAD"),
            reply(0x1234, 0x0002, 0x0001, session, b"\x99"),
        ]

    config = serve(responder, transport="udp")
    with SomeIpClient(config) as client:
        response = client.call(service=0x1234, instance=1, method=0x0002)

    assert response.payload == b"\x99"
    assert response.session_id == 1


def test_session_ids_advance_between_calls(serve):
    seen = []

    def responder(req):
        seen.append(session_of(req))
        return [reply(0x1234, 0x0002, 0x0001, session_of(req))]

    first = serve(responder)
    with SomeIpClient(first) as client:
        client.call(service=0x1234, instance=1, method=0x0002)
    second = serve(responder)
    with SomeIpClient(second) as client:
        client.call(service=0x1234, instance=1, method=0x0002)
        client.call(service=0x1234, instance=1, method=0x0002)

    assert seen[1:] == [1, 2]


def test_a_reply_with_our_session_but_another_service_is_rejected(serve):
    """Right envelope, wrong contents: never hand that back as the answer."""
    config = serve(lambda req: [reply(0x5555, 0x0002, 0x0001, session_of(req))])
    with SomeIpClient(config) as client:
        with pytest.raises(ProtocolError, match="expected 1234"):
            client.call(service=0x1234, instance=1, method=0x0002)


def test_a_peer_that_hangs_up_mid_message_is_an_error(serve):
    config = serve(
        lambda req: [reply(0x1234, 0x0002, 0x0001, session_of(req), b"\x01\x02")[:10]],
        hangup=True,
    )
    with SomeIpClient(config) as client:
        with pytest.raises(ProtocolError, match="closed after"):
            client.call(service=0x1234, instance=1, method=0x0002)


def test_a_silent_peer_times_out(serve):
    config = serve(lambda req: [])
    with SomeIpClient(SomeIpConfig(**{**config.__dict__, "timeout": 0.3})) as client:
        with pytest.raises((TimeoutError, socket.timeout)):
            client.call(service=0x1234, instance=1, method=0x0002)


def test_notify_expects_nothing_back(serve):
    config = serve(lambda req: [])
    with SomeIpClient(config) as client:
        client.notify(service=0x1234, instance=1, method=0x0003, payload=b"\x07")


def test_using_the_client_unconnected_is_an_error():
    client = SomeIpClient(SomeIpConfig(host="127.0.0.1", port=30509))
    with pytest.raises(ProtocolError, match="not connected"):
        client.call(service=0x1234, instance=1, method=0x0002)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"host": "", "port": 30509}, "host is required"),
        ({"host": "127.0.0.1", "port": 0}, "out of range"),
        ({"host": "127.0.0.1", "port": 30509, "transport": "sctp"}, "tcp"),
    ],
)
def test_an_unusable_config_fails_at_construction(kwargs, match):
    """No default host: an unconfigured target must fail here, not probe something."""
    with pytest.raises(NotConfigured, match=match):
        SomeIpConfig(**kwargs)
