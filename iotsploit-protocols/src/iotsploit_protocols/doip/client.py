"""A DoIP connection: routing activation, framing, one diagnostic exchange.

Replaces the transport half of the old ``DoIP_Mgr``. The differences that
matter, each of them a defect in what came before:

**Framing follows the length field.** The old code read exactly 13 bytes, slept
half a second, then read 2048 more. TCP guarantees neither that one ``recv`` is
one message nor that an acknowledgement arrives alone, so a coalesced or split
segment silently desynchronized the stream and every subsequent response was
attributed to the wrong request. Here the 8-byte header is read, its length
field is believed, and exactly that many bytes follow.

**One client is one connection to one ECU.** The old module exported a
process-wide singleton, so two ECUs could not be addressed at once and a
half-open socket poisoned every later caller.

**Nothing here knows about a vehicle.** No default host, no NIC name, no sudo,
no interactive prompt. A caller supplies a config; an unconfigured target fails
loudly rather than probing whatever used to live at a hardcoded address.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Optional

from iotsploit_protocols.errors import NotConfigured, ProtocolError

logger = logging.getLogger(__name__)

#: protocol_version, inverse_version, payload_type, payload_length.
HEADER_LEN = 8

#: ISO 13400-2 version 0x02, followed by its bitwise inverse. The pair is how a
#: receiver rejects a stream that is not DoIP at all.
PROTOCOL_VERSION = b"\x02\xfd"

#: The payload types this client uses. ISO 13400-2.
PT_GENERIC_NACK = 0x0000
PT_ROUTING_ACTIVATION_REQUEST = 0x0005
PT_ROUTING_ACTIVATION_RESPONSE = 0x0006
PT_ALIVE_CHECK_REQUEST = 0x0007
PT_ALIVE_CHECK_RESPONSE = 0x0008
PT_DIAGNOSTIC_MESSAGE = 0x8001
PT_DIAGNOSTIC_ACK = 0x8002
PT_DIAGNOSTIC_NACK = 0x8003

#: Routing activation response codes worth naming. 0x10 is the only success.
ROUTING_ACTIVATION_OK = 0x10
ROUTING_ACTIVATION_CODES = {
    0x00: "unknown source address",
    0x01: "all sockets registered and active",
    0x02: "source address does not match",
    0x03: "source address already registered",
    0x04: "missing authentication",
    0x05: "rejected confirmation",
    0x06: "unsupported activation type",
    0x10: "success",
}


class RoutingActivationFailed(ProtocolError):
    """The gateway refused to route for us. Nothing else can work until it does."""

    def __init__(self, code: int) -> None:
        self.code = code
        name = ROUTING_ACTIVATION_CODES.get(code, "unknown")
        super().__init__(f"routing activation refused: 0x{code:02X} ({name})")


@dataclass(frozen=True)
class DoipConfig:
    """Where to connect, and which ECU to address.

    ``host`` has no default on purpose. The address it replaces was a function
    default naming one vehicle's gateway, so an unconfigured bench quietly
    probed that address and reported its silence as a result.
    """

    host: str
    logical_address: int
    port: int = 13400
    tester_address: int = 0x0E80
    activation_type: int = 0x00
    timeout: float = 5.0

    def __post_init__(self) -> None:
        if not self.host:
            raise NotConfigured("DoIP host is required; there is no default")
        if not 0 < self.port < 65536:
            raise NotConfigured(f"DoIP port {self.port!r} is out of range")
        for name in ("logical_address", "tester_address"):
            value = getattr(self, name)
            if not 0 <= value <= 0xFFFF:
                raise NotConfigured(f"DoIP {name} 0x{value:X} is not a 16-bit address")


class DoipClient:
    """One TCP connection to one DoIP entity.

    Use as a context manager: routing activation happens on entry and the socket
    is closed on exit even when a request raises.
    """

    def __init__(self, config: DoipConfig) -> None:
        self.config = config
        self._sock: Optional[socket.socket] = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def __enter__(self) -> "DoipClient":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def connect(self) -> None:
        """Open the socket and activate routing.

        Routing activation is not optional politeness: until the gateway accepts
        it, diagnostic messages are discarded, and the old code's habit of
        pressing on regardless is why a refused activation looked like a silent
        ECU.
        """
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.config.timeout)
        sock.connect((self.config.host, self.config.port))
        self._sock = sock
        logger.debug("DoIP connected to %s:%d", self.config.host, self.config.port)
        try:
            self._activate_routing()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._sock.close()
        except OSError:
            logger.debug("DoIP socket close failed", exc_info=True)
        finally:
            self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    # ── exchanges ─────────────────────────────────────────────────────────

    def request(self, payload: bytes) -> bytes:
        """Send one UDS payload to the configured ECU and return the response.

        The positive/negative acknowledgement DoIP interposes (0x8002 / 0x8003)
        is consumed here rather than handed upward: it says the *gateway* took
        the message, which is not an answer to the diagnostic request and was
        the source of the old code's magic offsets.
        """
        self._send(PT_DIAGNOSTIC_MESSAGE, self._addresses() + payload)
        return self.read()

    def read(self) -> bytes:
        """The next diagnostic response, sending nothing.

        Used by the UDS layer after a responsePending: the ECU will send the
        real answer by itself, and re-sending the request would perform it
        twice.
        """
        while True:
            payload_type, body = self._read_message()

            if payload_type == PT_DIAGNOSTIC_ACK:
                logger.debug("DoIP ack")
                continue
            if payload_type == PT_DIAGNOSTIC_NACK:
                code = body[4] if len(body) > 4 else -1
                raise ProtocolError(f"DoIP refused the diagnostic message: 0x{code:02X}")
            if payload_type == PT_ALIVE_CHECK_REQUEST:
                # Answering keeps the socket registered. Ignoring it, as the old
                # code did, gets the connection dropped mid-session.
                self._send(PT_ALIVE_CHECK_RESPONSE, self._addresses()[:2])
                continue
            if payload_type == PT_GENERIC_NACK:
                code = body[0] if body else -1
                raise ProtocolError(f"DoIP header negative acknowledge: 0x{code:02X}")
            if payload_type == PT_DIAGNOSTIC_MESSAGE:
                # source(2) + target(2) then the UDS payload.
                return body[4:]

            logger.debug("DoIP ignoring payload type 0x%04X", payload_type)

    # ── internals ─────────────────────────────────────────────────────────

    def _addresses(self) -> bytes:
        return self.config.tester_address.to_bytes(2, "big") + self.config.logical_address.to_bytes(
            2, "big"
        )

    def _activate_routing(self) -> None:
        request = (
            self.config.tester_address.to_bytes(2, "big")
            + bytes([self.config.activation_type])
            + b"\x00\x00\x00\x00"
        )
        self._send(PT_ROUTING_ACTIVATION_REQUEST, request)

        payload_type, body = self._read_message()
        if payload_type != PT_ROUTING_ACTIVATION_RESPONSE:
            raise ProtocolError(
                f"expected routing activation response, got payload type 0x{payload_type:04X}"
            )
        if len(body) < 5:
            raise ProtocolError(f"routing activation response truncated: {len(body)} bytes")
        code = body[4]
        if code != ROUTING_ACTIVATION_OK:
            raise RoutingActivationFailed(code)
        logger.debug("DoIP routing activated for tester 0x%04X", self.config.tester_address)

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise ProtocolError("DoIP client is not connected; use it as a context manager")
        return self._sock

    def _send(self, payload_type: int, body: bytes) -> None:
        """Header plus body.

        Built by hand rather than through scapy's ``DoIP`` layer, which declares
        source_address/target_address as *conditional* fields for some payload
        types: handing it a body that already contains those addresses encodes
        them twice, once zeroed. The header is four fields and the parser here
        already reads it directly, so building it directly keeps one definition
        of the format instead of two that must agree.
        """
        header = (
            PROTOCOL_VERSION
            + payload_type.to_bytes(2, "big")
            + len(body).to_bytes(4, "big")
        )
        self._require_socket().sendall(header + body)

    def _read_message(self) -> tuple[int, bytes]:
        """One whole DoIP message: header, then exactly what it declares."""
        header = self._read_exactly(HEADER_LEN)
        payload_type = int.from_bytes(header[2:4], "big")
        declared = int.from_bytes(header[4:HEADER_LEN], "big")
        if declared > 0xFFFF:
            # A length this large is a desynchronized stream, not a real message.
            raise ProtocolError(f"implausible DoIP payload length {declared}")
        return payload_type, self._read_exactly(declared) if declared else b""

    def _read_exactly(self, count: int) -> bytes:
        sock = self._require_socket()
        chunks = []
        remaining = count
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ProtocolError(f"DoIP peer closed after {count - remaining} of {count} bytes")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
