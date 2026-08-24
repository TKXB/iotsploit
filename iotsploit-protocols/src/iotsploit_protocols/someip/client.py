"""A SOME/IP client: build a request, send it, match the response.

scapy is used as a **codec, not as a socket**. Its sending paths want root and a
live interface, which would make calling a method a privileged operation for no
reason; the wire format is the hard part and that is what scapy is for. So this
module builds and parses with ``scapy.contrib.automotive.someip`` and does I/O
on an ordinary socket.

Framing is done here rather than delegated, because scapy will not do it: given
two concatenated SOME/IP messages, ``SOMEIP(raw)`` returns one packet whose
payload is *both*. Over TCP, where one ``recv`` is not one message, that is the
same class of bug as reading a fixed 13 bytes and hoping. The length field is
authoritative and this module reads it.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Optional

from iotsploit_protocols.errors import NotConfigured, ProtocolError
from iotsploit_protocols.someip.codec import application_payload

logger = logging.getLogger(__name__)

#: Bytes before the payload: srv_id, sub_id, len, client_id, session_id,
#: proto_ver, iface_ver, msg_type, retcode.
HEADER_LEN = 16
#: srv_id(2) + sub_id(2) + len(4). Everything after this is covered by ``len``.
LEN_PREFIX = 8

TYPE_REQUEST = 0x00
TYPE_REQUEST_NO_RETURN = 0x01
TYPE_RESPONSE = 0x80
TYPE_ERROR = 0x81

RETURN_CODE_NAMES = {
    0x00: "E_OK",
    0x01: "E_NOT_OK",
    0x02: "E_UNKNOWN_SERVICE",
    0x03: "E_UNKNOWN_METHOD",
    0x04: "E_NOT_READY",
    0x05: "E_NOT_REACHABLE",
    0x06: "E_TIMEOUT",
    0x07: "E_WRONG_PROTOCOL_VERSION",
    0x08: "E_WRONG_INTERFACE_VERSION",
    0x09: "E_MALFORMED_MESSAGE",
    0x0A: "E_WRONG_MESSAGE_TYPE",
}


@dataclass(frozen=True)
class SomeIpConfig:
    """Where to send SOME/IP, and as whom.

    ``host`` has no default on purpose. A helper that falls back to a built-in
    address probes whatever happens to be at that address and reports its
    silence as a finding. An unconfigured target must fail, loudly, here.
    """

    host: str
    port: int
    transport: str = "tcp"
    client_id: int = 0x0001
    timeout: float = 5.0

    def __post_init__(self) -> None:
        if not self.host:
            raise NotConfigured("SOME/IP host is required; there is no default")
        if not 0 < self.port < 65536:
            raise NotConfigured(f"SOME/IP port {self.port!r} is out of range")
        if self.transport not in ("tcp", "udp"):
            raise NotConfigured(f"transport must be 'tcp' or 'udp', got {self.transport!r}")


@dataclass(frozen=True)
class SomeIpResponse:
    """One reply, already parsed.

    ``ok`` is the only thing most callers need. It is deliberately not "did we
    get bytes back": an ERROR message with E_UNKNOWN_METHOD is a perfectly
    well-formed reply that means no.
    """

    service_id: int
    method_id: int
    client_id: int
    session_id: int
    message_type: int
    return_code: int
    payload: bytes

    @property
    def ok(self) -> bool:
        return self.message_type == TYPE_RESPONSE and self.return_code == 0x00

    @property
    def return_code_name(self) -> str:
        return RETURN_CODE_NAMES.get(self.return_code, f"0x{self.return_code:02X}")


class SomeIpClient:
    """One client is one socket to one endpoint.

    Not a singleton and not shared: two endpoints means two clients. Use it as a
    context manager so the socket is closed even when a call raises.
    """

    def __init__(self, config: SomeIpConfig) -> None:
        self.config = config
        self._sock: Optional[socket.socket] = None
        # Wraps at 16 bits like the field it fills. Starts at 1 because 0 is
        # conventionally "session handling disabled".
        self._session_id = 0

    # ── lifecycle ─────────────────────────────────────────────────────────

    def __enter__(self) -> "SomeIpClient":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def connect(self) -> None:
        if self._sock is not None:
            return
        kind = socket.SOCK_STREAM if self.config.transport == "tcp" else socket.SOCK_DGRAM
        sock = socket.socket(socket.AF_INET, kind)
        sock.settimeout(self.config.timeout)
        # connect() on a UDP socket sets the default peer; it does not handshake,
        # so this is cheap and lets send()/recv() be used for both transports.
        sock.connect((self.config.host, self.config.port))
        self._sock = sock
        logger.debug(
            "SOME/IP connected %s://%s:%d", self.config.transport, self.config.host, self.config.port
        )

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.close()
        except OSError:
            logger.debug("SOME/IP socket close failed", exc_info=True)
        finally:
            self._sock = None

    # ── requests ──────────────────────────────────────────────────────────

    def call(
        self,
        service: int,
        instance: int,
        method: int,
        payload: bytes = b"",
        interface_version: int = 0x01,
    ) -> SomeIpResponse:
        """Send a request and wait for the matching response.

        ``instance`` is accepted because callers think in service instances, but
        it is not on the wire: SOME/IP addresses an instance by *endpoint*, and
        the endpoint is what this client is connected to. It is used for logging
        and to keep call sites honest about which instance they meant.
        """
        session_id = self._next_session_id()
        request = self._build(
            service, method, session_id, TYPE_REQUEST, payload, interface_version
        )
        logger.debug(
            "SOME/IP -> service=%04X instance=%04X method=%04X session=%d len=%d",
            service, instance, method, session_id, len(payload),
        )
        self._send(request)
        return self._await_response(service, method, session_id)

    def notify(
        self,
        service: int,
        instance: int,
        method: int,
        payload: bytes = b"",
        interface_version: int = 0x01,
    ) -> None:
        """Fire-and-forget. No response is expected and none is waited for."""
        session_id = self._next_session_id()
        logger.debug(
            "SOME/IP -> (no return) service=%04X instance=%04X method=%04X session=%d",
            service, instance, method, session_id,
        )
        self._send(
            self._build(
                service, method, session_id, TYPE_REQUEST_NO_RETURN, payload, interface_version
            )
        )

    # ── internals ─────────────────────────────────────────────────────────

    def _next_session_id(self) -> int:
        # 1..0xFFFF, skipping 0.
        self._session_id = (self._session_id % 0xFFFF) + 1
        return self._session_id

    def _build(
        self,
        service: int,
        method: int,
        session_id: int,
        message_type: int,
        payload: bytes,
        interface_version: int,
    ) -> bytes:
        from scapy.contrib.automotive.someip import SOMEIP
        from scapy.packet import Raw

        packet = SOMEIP(
            srv_id=service,
            sub_id=method,
            client_id=self.config.client_id,
            session_id=session_id,
            iface_ver=interface_version,
            msg_type=message_type,
        )
        if payload:
            packet = packet / Raw(payload)
        return bytes(packet)

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise ProtocolError("SOME/IP client is not connected; use it as a context manager")
        return self._sock

    def _send(self, data: bytes) -> None:
        self._require_socket().sendall(data)

    def _await_response(self, service: int, method: int, session_id: int) -> SomeIpResponse:
        """Read messages until the one we asked for arrives.

        Responses can interleave -- notably over UDP, where an event from
        another service may land between our request and its answer. Matching on
        (client_id, session_id) is what keeps a reply attached to its request;
        anything else is logged and dropped rather than returned to the caller
        as if it were the answer.
        """
        while True:
            response = self._parse(self._read_message())
            if response.client_id == self.config.client_id and response.session_id == session_id:
                if response.service_id != service or response.method_id != method:
                    # Same session id, different message id: the peer is
                    # confused or something is spoofing. Do not silently accept.
                    raise ProtocolError(
                        f"response session {session_id} carries service "
                        f"{response.service_id:04X}/{response.method_id:04X}, "
                        f"expected {service:04X}/{method:04X}"
                    )
                return response
            logger.debug(
                "SOME/IP dropping unrelated message client=%04X session=%d",
                response.client_id, response.session_id,
            )

    def _read_message(self) -> bytes:
        """One whole message, using the length field rather than hoping.

        UDP delivers a datagram at a time, but a truncated or padded datagram
        still has to agree with its own length field, so both transports are
        validated the same way.
        """
        sock = self._require_socket()
        if self.config.transport == "udp":
            datagram = sock.recv(65535)
            declared = self._declared_length(datagram)
            if len(datagram) < LEN_PREFIX + declared:
                raise ProtocolError(
                    f"SOME/IP datagram is {len(datagram)} bytes but declares "
                    f"{LEN_PREFIX + declared}"
                )
            return datagram[: LEN_PREFIX + declared]

        head = self._read_exactly(LEN_PREFIX)
        declared = self._declared_length(head)
        return head + self._read_exactly(declared)

    @staticmethod
    def _declared_length(data: bytes) -> int:
        if len(data) < LEN_PREFIX:
            raise ProtocolError(f"SOME/IP message truncated: {len(data)} bytes")
        declared = int.from_bytes(data[4:LEN_PREFIX], "big")
        if declared < HEADER_LEN - LEN_PREFIX:
            raise ProtocolError(f"SOME/IP length field {declared} is shorter than the header")
        return declared

    def _read_exactly(self, count: int) -> bytes:
        sock = self._require_socket()
        chunks = []
        remaining = count
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ProtocolError(
                    f"SOME/IP peer closed after {count - remaining} of {count} bytes"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @staticmethod
    def _parse(raw: bytes) -> SomeIpResponse:
        from scapy.contrib.automotive.someip import SOMEIP

        packet = SOMEIP(raw)
        return SomeIpResponse(
            service_id=packet.srv_id,
            method_id=packet.sub_id,
            client_id=packet.client_id,
            session_id=packet.session_id,
            message_type=int(packet.msg_type),
            return_code=int(packet.retcode),
            payload=application_payload(packet),
        )
