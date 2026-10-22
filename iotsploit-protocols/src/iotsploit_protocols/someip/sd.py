"""SOME/IP Service Discovery: what a segment announces, and what a host admits to.

Two ways round, because one of them does not always work:

``listen()`` is passive. ECUs announce OfferService on the SD multicast group by
themselves, so it enumerates a bus without putting anything on it. It is the
right tool on a bench cabled to the segment.

``find()`` is active: it sends a FindService and reads the OfferService replies.
It exists because multicast does not always reach you. Across a router or a VPN
the group is usually not forwarded, so a passive listen sits silent and reports
"no services" about a bus full of them -- a wrong answer rather than an error.
Sent to one host, ``find()`` needs no multicast at all.

No root is needed either way. Joining a multicast group is an unprivileged
socket option; it is *raw* sockets that need privileges, and this uses none.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from iotsploit_protocols.errors import NotConfigured
from iotsploit_protocols.someip.codec import application_payload

logger = logging.getLogger(__name__)

#: The SD port assigned by the SOME/IP specification. A standard number, not a
#: description of any particular vehicle, so it may carry a default.
DEFAULT_SD_PORT = 30490

#: The multicast group the specification names for service discovery. Also a
#: constant of the protocol rather than of a vehicle -- and unlike a host
#: address, a wrong group discovers nothing rather than probing a stranger.
DEFAULT_SD_GROUP = "224.244.224.245"

#: SD entry type for OfferService. FindService (0x00) shares the same layout.
ENTRY_TYPE_OFFER = 0x01

#: SD option types carrying a reachable endpoint.
OPTION_IP4_ENDPOINT = 0x04

L4_PROTO_NAMES = {6: "tcp", 17: "udp"}


@dataclass(frozen=True)
class SdConfig:
    """Which segment to listen on.

    ``group`` and ``interface`` describe an Ethernet segment rather than a
    component -- every ECU on the segment shares them -- so they are supplied by
    the caller rather than read from any one component's facet.

    The two fields are easy to confuse, and the kernel is no help: joining a
    group at a unicast address fails with a bare ``EINVAL``. So the confusion is
    diagnosed here, where the two values are side by side and the message can
    say which one was probably meant.
    """

    group: str
    interface: Optional[str] = None
    port: int = DEFAULT_SD_PORT

    def __post_init__(self) -> None:
        if not self.group:
            raise NotConfigured("SD multicast group is required; there is no default")
        if not 0 < self.port < 65536:
            raise NotConfigured(f"SD port {self.port!r} is out of range")

        try:
            address = ipaddress.ip_address(self.group)
        except ValueError:
            raise NotConfigured(
                f"SD group {self.group!r} is not an IP address. Service discovery "
                f"listens on an IPv4 multicast group such as {DEFAULT_SD_GROUP}."
            ) from None
        if not isinstance(address, ipaddress.IPv4Address):
            raise NotConfigured(
                f"SD group {self.group!r} is IPv6; this listener is IPv4 only."
            )
        if not address.is_multicast:
            raise NotConfigured(
                f"SD group {self.group!r} is a unicast address, and a multicast "
                f"group must be in 224.0.0.0/4 (the SOME/IP default is "
                f"{DEFAULT_SD_GROUP}). If {self.group!r} is the local address of "
                f"the interface you want to listen on, pass it as 'interface' "
                f"instead of 'sd_group'."
            )


@dataclass(frozen=True)
class ServiceOffer:
    """One announced service instance.

    ``endpoints`` are plain tuples of ``(ip, port, "tcp"|"udp")`` so a caller
    never has to import scapy to read a result.
    """

    service_id: int
    instance_id: int
    major_version: int
    minor_version: int
    ttl: int
    endpoints: List[Tuple[str, int, str]] = field(default_factory=list)
    source: Optional[str] = None

    @property
    def canonical_id(self) -> str:
        from iotsploit_protocols.someip.facet import canonical_service_id

        return canonical_service_id(self.service_id, self.instance_id)


class ServiceDiscovery:
    """Listens on the SD multicast group and reports what it heard."""

    def __init__(self, config: SdConfig) -> None:
        self.config = config

    def listen(self, timeout: float = 10.0) -> List[ServiceOffer]:
        """Collect offers for ``timeout`` seconds, announced by anyone.

        Returns one entry per distinct (service, instance), latest wins: an ECU
        re-announcing the same service during the window is one service, not
        several. Deduplicating here rather than in the caller keeps the "what is
        on this segment" answer stable regardless of how long you listened.
        """
        with self._socket(join_group=True) as sock:
            offers = self._collect(sock, timeout)
        logger.info("SD heard %d service instance(s) on %s", len(offers), self.config.group)
        return offers

    def find(
        self,
        host: Optional[str] = None,
        timeout: float = 3.0,
        service_id: int = 0xFFFF,
        instance_id: int = 0xFFFF,
    ) -> List[ServiceOffer]:
        """Ask, rather than wait. Returns the OfferService replies.

        ``host`` unset sends the FindService to the multicast group; set, it goes
        to that one host and no multicast is involved at any point, which is what
        makes this work across a router or a VPN.

        The defaults are the specification's wildcards -- any service, any
        instance -- so the bare call is "tell me everything you offer".
        """
        destination = host or self.config.group
        with self._socket(join_group=host is None) as sock:
            datagram = self._find_datagram(service_id, instance_id, ttl=int(timeout) + 1)
            logger.debug("SD FindService -> %s:%d", destination, self.config.port)
            try:
                sock.sendto(datagram, (destination, self.config.port))
            except OSError as exc:
                raise NotConfigured(
                    f"cannot send FindService to {destination}:{self.config.port}: "
                    f"{exc.strerror or exc}"
                ) from None
            offers = self._collect(sock, timeout)
        logger.info("SD FindService to %s answered with %d instance(s)", destination, len(offers))
        return offers

    # ── internals ─────────────────────────────────────────────────────────

    def _collect(self, sock: socket.socket, timeout: float) -> List[ServiceOffer]:
        """Read offers until ``timeout`` expires, deduplicated by (service, instance)."""
        deadline = time.monotonic() + timeout
        offers: dict[tuple[int, int], ServiceOffer] = {}
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                datagram, sender = sock.recvfrom(65535)
            except (TimeoutError, socket.timeout):
                break
            except OSError:
                logger.debug("SD receive failed", exc_info=True)
                break
            for offer in self._parse(datagram, sender[0]):
                offers[(offer.service_id, offer.instance_id)] = offer
        return list(offers.values())

    @staticmethod
    def _find_datagram(service_id: int, instance_id: int, ttl: int) -> bytes:
        from scapy.contrib.automotive.someip import SD, SDEntry_Service, SOMEIP

        entry = SDEntry_Service(
            type=0x00,  # FindService
            srv_id=service_id,
            inst_id=instance_id,
            # 0xFF / 0xFFFFFFFF are the spec's "any version" wildcards.
            major_ver=0xFF,
            minor_ver=0xFFFFFFFF,
            ttl=ttl,
            n_opt_1=0,
            n_opt_2=0,
        )
        # UNICAST says we accept unicast replies, which is the entire point when
        # the request did not go to a group.
        return bytes(SOMEIP() / SD(flags="UNICAST", entry_array=[entry]))

    def _socket(self, join_group: bool) -> socket.socket:
        """A UDP socket bound to the SD port, optionally joined to the group.

        Binding to the SD port matters even for a unicast find: the ECU replies
        to the port it was asked from, so an ephemeral source port would send
        the answer somewhere nobody is listening.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.config.port))
        if not join_group:
            return sock
        interface = self._interface_address()
        try:
            # Egress selection for anything we send to the group. Without it the
            # kernel picks by route, which on a multi-NIC host is a different
            # NIC from the one we joined on.
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface)
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(self.config.group) + interface,
            )
        except OSError as exc:
            sock.close()
            # ENODEV/EADDRNOTAVAIL here mean the interface is not one of this
            # host's own. The errno alone sends people looking at the ECU, so
            # say what was wrong and what this host actually has.
            raise NotConfigured(
                f"cannot join {self.config.group} on interface "
                f"{self.config.interface!r}: {exc.strerror or exc}. "
                f"'interface' must name a NIC on this host, or carry that NIC's "
                f"own address. Available here: {_local_interfaces() or 'unknown'}"
            ) from None
        return sock

    def _interface_address(self) -> bytes:
        """Which local interface joins the group.

        INADDR_ANY lets the kernel choose, which is wrong on a bench with
        several NICs -- the join silently lands on the wrong one and the listen
        returns nothing, looking exactly like "no services on this bus".
        """
        if not self.config.interface:
            logger.warning(
                "SD joining %s on the default interface. On a host with several "
                "NICs the kernel's choice is often the wrong segment, and the "
                "result is an empty sweep that reads as 'no services'. Pass an "
                "interface name or local IP to be sure.",
                self.config.group,
            )
            return struct.pack("=I", socket.INADDR_ANY)
        try:
            return socket.inet_aton(socket.gethostbyname(self.config.interface))
        except OSError:
            pass
        address = _interface_ipv4(self.config.interface)
        if address is None:
            raise NotConfigured(
                f"interface {self.config.interface!r} has no IPv4 address to join the group with"
            )
        return socket.inet_aton(address)

    @staticmethod
    def _parse(datagram: bytes, sender: str) -> List[ServiceOffer]:
        from scapy.contrib.automotive.someip import SD, SOMEIP

        try:
            packet = SOMEIP(datagram)
            payload = application_payload(packet)
            if not payload:
                return []
            sd = SD(payload)
        except Exception:
            logger.debug("SD datagram from %s did not parse", sender, exc_info=True)
            return []

        options = list(getattr(sd, "option_array", []) or [])
        offers = []
        for entry in getattr(sd, "entry_array", []) or []:
            if int(getattr(entry, "type", -1)) != ENTRY_TYPE_OFFER:
                continue
            ttl = int(getattr(entry, "ttl", 0))
            if ttl == 0:
                # TTL 0 is StopOffer: the service is going away, not appearing.
                continue
            offers.append(
                ServiceOffer(
                    service_id=int(entry.srv_id),
                    instance_id=int(entry.inst_id),
                    major_version=int(getattr(entry, "major_ver", 0)),
                    minor_version=int(getattr(entry, "minor_ver", 0)),
                    ttl=ttl,
                    endpoints=_entry_endpoints(entry, options),
                    source=sender,
                )
            )
        return offers


def _entry_endpoints(entry, options) -> List[Tuple[str, int, str]]:
    """The endpoint options an entry points at.

    An SD entry does not carry its endpoint; it carries two (index, count) runs
    into the message-wide option array. Resolving that here is why callers get
    an address instead of a pair of integers.
    """
    endpoints = []
    runs = (
        (int(getattr(entry, "index_1", 0)), int(getattr(entry, "n_opt_1", 0))),
        (int(getattr(entry, "index_2", 0)), int(getattr(entry, "n_opt_2", 0))),
    )
    for index, count in runs:
        for option in options[index : index + count]:
            if int(getattr(option, "type", -1)) != OPTION_IP4_ENDPOINT:
                continue
            proto = L4_PROTO_NAMES.get(int(getattr(option, "l4_proto", 0)), "unknown")
            endpoints.append((str(option.addr), int(option.port), proto))
    return endpoints


def _local_interfaces() -> str:
    """``name=address`` for every IPv4 NIC on this host, for error messages."""
    import psutil

    entries = []
    for name, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family == socket.AF_INET:
                entries.append(f"{name}={address.address}")
    return ", ".join(entries)


def _interface_ipv4(name: str) -> Optional[str]:
    """The IPv4 address of a named NIC, or None.

    Uses psutil so interface enumeration remains portable.
    """
    import psutil

    addresses = psutil.net_if_addrs().get(name, [])
    for address in addresses:
        if address.family == socket.AF_INET:
            return address.address
    return None
