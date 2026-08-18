"""UDS on top of a DoIP connection.

Separate from ``client.py`` because UDS is not DoIP: the same services run over
ISO-TP on CAN, and a layer that knows about session control should not also know
about routing activation. ``UdsClient`` needs only something with a
``request(bytes) -> bytes`` method.

What this replaces was a set of magic offsets -- ``resp_buf[12]``,
``resp_buf[-3]``, ``resp_buf[-5]`` -- each call site indexing the raw buffer
differently and each one wrong for some message shape. One layer parses the
response once and hands back something with a name.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from iotsploit_protocols.errors import ProtocolError

logger = logging.getLogger(__name__)

NEGATIVE_RESPONSE = 0x7F
#: requestCorrectlyReceived-ResponsePending. The ECU is working; wait for it.
NRC_RESPONSE_PENDING = 0x78

#: Services used here. Names, so no caller writes a bare byte again.
SERVICE_DIAGNOSTIC_SESSION_CONTROL = 0x10
SERVICE_ROUTINE_CONTROL = 0x31
SERVICE_READ_DATA_BY_IDENTIFIER = 0x22
SERVICE_SECURITY_ACCESS = 0x27
SERVICE_TESTER_PRESENT = 0x3E

SESSION_DEFAULT = 0x01
SESSION_PROGRAMMING = 0x02
SESSION_EXTENDED = 0x03

ROUTINE_START = 0x01
ROUTINE_STOP = 0x02
ROUTINE_REQUEST_RESULTS = 0x03


class Transport(Protocol):
    """Anything that can carry one UDS payload and bring back the answer."""

    def request(self, payload: bytes) -> bytes: ...

    def read(self) -> bytes:
        """The next response with no new request.

        Needed for responsePending: after a 0x78 the ECU sends the real answer
        unprompted, so re-sending would put the request on the bus twice --
        which for a routine that does something physical is not a retry, it is
        doing it again.
        """
        ...


@dataclass(frozen=True)
class UdsResponse:
    """One parsed UDS response.

    ``ok`` and ``nrc`` are the whole interface most callers need. A negative
    response is not an exception here: "the ECU said no" is frequently the
    finding being looked for, and raising would make the normal case awkward.
    Callers that prefer an exception can check ``ok`` and raise their own.
    """

    service: int
    data: bytes
    nrc: Optional[int] = None
    raw: bytes = b""

    @property
    def ok(self) -> bool:
        return self.nrc is None

    @property
    def nrc_name(self) -> str:
        if self.nrc is None:
            return ""
        return _nrc_name(self.nrc)


def _nrc_name(nrc: int) -> str:
    """The standard label for a negative response code, via scapy's table."""
    try:
        from scapy.contrib.automotive.uds import UDS_NR

        name = UDS_NR.fields_desc[1].i2s.get(nrc)
        if name:
            return str(name)
    except Exception:  # pragma: no cover - scapy layout changed
        logger.debug("could not resolve NRC name from scapy", exc_info=True)
    return f"0x{nrc:02X}"


class UdsClient:
    """UDS requests over any transport that can carry them.

    ``response_pending_attempts`` bounds how many 0x78 replies are waited
    through. The old code had this handling commented out, which meant a busy
    ECU -- the normal state during a routine -- was recorded as a failure.
    """

    def __init__(
        self,
        transport: Transport,
        response_pending_attempts: int = 10,
        response_pending_deadline: float = 30.0,
    ) -> None:
        self.transport = transport
        self.response_pending_attempts = response_pending_attempts
        self.response_pending_deadline = response_pending_deadline

    # ── services ──────────────────────────────────────────────────────────

    def session(self, kind: int = SESSION_DEFAULT) -> UdsResponse:
        return self.request(bytes([SERVICE_DIAGNOSTIC_SESSION_CONTROL, kind]))

    def tester_present(self, suppress_response: bool = False) -> UdsResponse:
        sub = 0x80 if suppress_response else 0x00
        return self.request(bytes([SERVICE_TESTER_PRESENT, sub]))

    def read_did(self, did: int) -> UdsResponse:
        return self.request(bytes([SERVICE_READ_DATA_BY_IDENTIFIER]) + did.to_bytes(2, "big"))

    def routine(self, control: int, routine_id: int, data: bytes = b"") -> UdsResponse:
        return self.request(
            bytes([SERVICE_ROUTINE_CONTROL, control]) + routine_id.to_bytes(2, "big") + data
        )

    def is_alive(self) -> bool:
        """Whether the ECU answers at all.

        A negative response still counts: it proves something is there and
        speaking UDS, which is what "alive" means here.
        """
        try:
            self.session(SESSION_DEFAULT)
            return True
        except (ProtocolError, TimeoutError, OSError):
            return False

    def security_access(
        self,
        level: int,
        pin: bytes,
        key_fn: Callable[[bytes, bytes], bytes],
    ) -> bool:
        """Request a seed, derive the key with ``key_fn``, send it back.

        ``key_fn`` is passed in rather than looked up by name. The derivation is
        one manufacturer's proprietary algorithm; a library that shipped a
        registry of them would be a library that ships them.

        ``level`` is the requestSeed sub-function; the sendKey sub-function is
        ``level + 1``, as ISO 14229 defines.
        """
        seed_response = self.request(bytes([SERVICE_SECURITY_ACCESS, level]))
        if not seed_response.ok:
            logger.error("security access: seed refused (%s)", seed_response.nrc_name)
            return False

        # The response is 67 <echoed sub-function> <seed...>. The echo is not
        # part of the seed, and feeding it to the derivation yields a key the
        # ECU will reject -- which looks exactly like a wrong PIN.
        if len(seed_response.data) < 2:
            raise ProtocolError("security access: ECU returned an empty seed")
        echoed, seed = seed_response.data[0], seed_response.data[1:]
        if echoed != level:
            raise ProtocolError(
                f"security access: ECU echoed sub-function 0x{echoed:02X}, "
                f"expected 0x{level:02X}"
            )
        if not seed:
            raise ProtocolError("security access: ECU returned an empty seed")
        if not any(seed):
            # An all-zero seed means the ECU considers this level already open.
            logger.info("security access: level 0x%02X already unlocked", level)
            return True

        key = key_fn(seed, pin)
        key_response = self.request(bytes([SERVICE_SECURITY_ACCESS, level + 1]) + key)
        if not key_response.ok:
            logger.error("security access: key rejected (%s)", key_response.nrc_name)
            return False
        return True

    # ── the one place a response is parsed ────────────────────────────────

    def request(self, payload: bytes) -> UdsResponse:
        """Send a UDS payload, waiting through any responsePending replies."""
        if not payload:
            raise ValueError("UDS payload must not be empty")
        service = payload[0]
        deadline = time.monotonic() + self.response_pending_deadline

        raw = self.transport.request(payload)

        for attempt in range(1, self.response_pending_attempts + 1):
            response = self._parse(service, raw)
            if response.nrc != NRC_RESPONSE_PENDING:
                return response
            if time.monotonic() >= deadline:
                raise ProtocolError(
                    f"UDS service 0x{service:02X} still pending after "
                    f"{self.response_pending_deadline}s"
                )
            logger.debug("UDS service 0x%02X response pending (%d)", service, attempt)
            # Read, do not re-send: the ECU is already working on it.
            raw = self.transport.read()

        raise ProtocolError(
            f"UDS service 0x{service:02X} stayed pending for "
            f"{self.response_pending_attempts} attempts"
        )

    @staticmethod
    def _parse(service: int, raw: bytes) -> UdsResponse:
        if not raw:
            raise ProtocolError(f"UDS service 0x{service:02X}: empty response")

        if raw[0] == NEGATIVE_RESPONSE:
            if len(raw) < 3:
                raise ProtocolError(f"UDS negative response truncated: {raw.hex()}")
            echoed, nrc = raw[1], raw[2]
            if echoed != service:
                raise ProtocolError(
                    f"UDS negative response echoes service 0x{echoed:02X}, "
                    f"expected 0x{service:02X}"
                )
            return UdsResponse(service=service, data=b"", nrc=nrc, raw=raw)

        expected = service + 0x40
        if raw[0] != expected:
            raise ProtocolError(
                f"UDS response starts 0x{raw[0]:02X}, expected 0x{expected:02X} "
                f"for service 0x{service:02X}"
            )
        return UdsResponse(service=service, data=raw[1:], nrc=None, raw=raw)


class DoipUdsClient(UdsClient):
    """A :class:`UdsClient` bound to a :class:`~.client.DoipClient`.

    Exists only so callers do not have to write ``UdsClient(DoipClient(cfg))``
    and remember which one is the context manager.
    """

    def __init__(self, doip_client, **kwargs) -> None:
        super().__init__(doip_client, **kwargs)
        self.doip = doip_client

    def __enter__(self) -> "DoipUdsClient":
        self.doip.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.doip.close()
