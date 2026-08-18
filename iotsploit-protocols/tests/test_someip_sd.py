"""Service discovery: what a segment announces, and what we make of it.

The parsing under test is ours -- resolving an entry's (index, count) runs into
the message-wide option array, dropping StopOffer, deduplicating repeats. The
multicast path is exercised over real loopback so the group join is not mocked
away; the datagram-level cases go straight at the parser, because standing up a
multicast group to assert a TTL would test the kernel.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

import pytest

from iotsploit_protocols.errors import NotConfigured
from iotsploit_protocols.someip import SdConfig, ServiceDiscovery

pytestmark = pytest.mark.unit

GROUP = "224.244.224.245"


def offer_datagram(entries, options):
    """One SD notification carrying the given entries and options."""
    from scapy.contrib.automotive.someip import SD, SOMEIP

    return bytes(SOMEIP() / SD(entry_array=entries, option_array=options))


def service_entry(srv_id=0x1234, inst_id=0x0001, ttl=3, index_1=0, n_opt_1=1, entry_type=0x01):
    from scapy.contrib.automotive.someip import SDEntry_Service

    return SDEntry_Service(
        type=entry_type,
        srv_id=srv_id,
        inst_id=inst_id,
        major_ver=1,
        minor_ver=0,
        ttl=ttl,
        index_1=index_1,
        n_opt_1=n_opt_1,
    )


def endpoint(addr="198.18.34.10", port=30509, proto=6):
    from scapy.contrib.automotive.someip import SDOption_IP4_EndPoint

    return SDOption_IP4_EndPoint(addr=addr, l4_proto=proto, port=port)


def parse(datagram, sender="198.18.34.10"):
    return ServiceDiscovery._parse(datagram, sender)


# ── parsing ───────────────────────────────────────────────────────────────


def test_an_offer_yields_its_service_and_endpoint():
    offers = parse(offer_datagram([service_entry()], [endpoint()]))

    assert len(offers) == 1
    assert offers[0].service_id == 0x1234
    assert offers[0].instance_id == 0x0001
    assert offers[0].endpoints == [("198.18.34.10", 30509, "tcp")]


def test_the_canonical_id_is_the_observation_subject_form():
    """This string is the join key against the reference catalog."""
    offers = parse(offer_datagram([service_entry(srv_id=0x1234, inst_id=1)], [endpoint()]))

    assert offers[0].canonical_id == "1234:0001"


def test_a_stop_offer_is_not_an_offer():
    """TTL 0 means the service is going away. Recording it as present inverts the finding."""
    assert parse(offer_datagram([service_entry(ttl=0)], [endpoint()])) == []


def test_a_find_service_entry_is_ignored():
    """Someone else asking a question is not an announcement."""
    assert parse(offer_datagram([service_entry(entry_type=0x00)], [endpoint()])) == []


def test_each_entry_gets_only_the_options_it_points_at():
    """The whole point of the index/count runs: two services, two endpoints, no crossover."""
    entries = [
        service_entry(srv_id=0x1111, index_1=0, n_opt_1=1),
        service_entry(srv_id=0x2222, index_1=1, n_opt_1=1),
    ]
    options = [endpoint(addr="198.18.34.10", port=100), endpoint(addr="198.18.34.20", port=200)]

    by_id = {o.service_id: o for o in parse(offer_datagram(entries, options))}

    assert by_id[0x1111].endpoints == [("198.18.34.10", 100, "tcp")]
    assert by_id[0x2222].endpoints == [("198.18.34.20", 200, "tcp")]


def test_a_service_with_no_options_still_reports():
    """An offer without an endpoint is odd but real; dropping it would hide a service."""
    offers = parse(offer_datagram([service_entry(n_opt_1=0)], []))

    assert len(offers) == 1
    assert offers[0].endpoints == []


def test_udp_and_tcp_endpoints_are_labelled():
    offers = parse(
        offer_datagram([service_entry(n_opt_1=2)], [endpoint(proto=6), endpoint(proto=17)])
    )

    assert [proto for _, _, proto in offers[0].endpoints] == ["tcp", "udp"]


def test_the_sender_address_is_recorded():
    """Which host announced it -- needed later to attach an offer to a component."""
    offers = parse(offer_datagram([service_entry()], [endpoint()]), sender="198.18.34.99")

    assert offers[0].source == "198.18.34.99"


def test_a_datagram_that_is_not_sd_is_dropped_quietly():
    """A stray packet on the group must not take the sweep down."""
    assert parse(b"\x00\x01\x02\x03") == []


# ── listening ─────────────────────────────────────────────────────────────


def send_to_group(datagrams, port, delay=0.1):
    def run():
        time.sleep(delay)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1"))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        for datagram in datagrams:
            sock.sendto(datagram, (GROUP, port))
        sock.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


@pytest.fixture
def sd_port():
    """A free UDP port, so a real SD listener on 30490 cannot interfere."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.mark.integration
def test_listen_collects_offers_from_the_group(sd_port):
    send_to_group([offer_datagram([service_entry()], [endpoint()])], sd_port)

    offers = ServiceDiscovery(
        SdConfig(group=GROUP, interface="127.0.0.1", port=sd_port)
    ).listen(timeout=2.0)

    assert [o.canonical_id for o in offers] == ["1234:0001"]


@pytest.mark.integration
def test_a_service_announced_twice_is_one_service(sd_port):
    """An ECU re-announcing during the window must not look like two instances."""
    datagram = offer_datagram([service_entry()], [endpoint()])
    send_to_group([datagram, datagram], sd_port)

    offers = ServiceDiscovery(
        SdConfig(group=GROUP, interface="127.0.0.1", port=sd_port)
    ).listen(timeout=2.0)

    assert len(offers) == 1


@pytest.mark.integration
def test_a_quiet_segment_returns_nothing_rather_than_hanging(sd_port):
    started = time.monotonic()

    offers = ServiceDiscovery(
        SdConfig(group=GROUP, interface="127.0.0.1", port=sd_port)
    ).listen(timeout=0.5)

    assert offers == []
    assert time.monotonic() - started < 5.0


# ── configuration ─────────────────────────────────────────────────────────


def test_a_missing_group_is_refused():
    with pytest.raises(NotConfigured, match="group is required"):
        SdConfig(group="")


def test_a_unicast_group_says_so_and_names_the_likely_mistake():
    """The kernel's answer to this is a bare EINVAL, which explains nothing.

    Passing one's own interface address as the group is the easy confusion --
    the two fields sit next to each other and both hold an IP -- so the message
    has to name it.
    """
    with pytest.raises(NotConfigured) as exc:
        SdConfig(group="10.8.0.10")

    message = str(exc.value)
    assert "unicast" in message
    assert "224.0.0.0/4" in message
    assert "'interface'" in message


def test_something_that_is_not_an_address_at_all_is_refused():
    with pytest.raises(NotConfigured, match="not an IP address"):
        SdConfig(group="eth0")


def test_an_ipv6_group_is_refused_rather_than_failing_in_the_socket():
    with pytest.raises(NotConfigured, match="IPv6"):
        SdConfig(group="ff02::1")


def test_a_port_out_of_range_is_refused():
    with pytest.raises(NotConfigured, match="out of range"):
        SdConfig(group=GROUP, port=0)


def test_a_valid_group_is_accepted():
    assert SdConfig(group=GROUP).group == GROUP


def test_an_unknown_interface_is_refused_rather_than_guessed(monkeypatch):
    """Joining on the wrong NIC returns nothing, which reads exactly like 'no services'."""
    monkeypatch.setattr("iotsploit_protocols.someip.sd._interface_ipv4", lambda name: None)
    discovery = ServiceDiscovery(SdConfig(group=GROUP, interface="nope0"))

    with pytest.raises(NotConfigured, match="no IPv4 address"):
        discovery._interface_address()


@pytest.fixture
def responder(sd_port):
    """A fake ECU that answers FindService with one OfferService.

    It lives on 127.0.0.2 rather than 127.0.0.1 so the reply genuinely travels
    to the finder's socket. Same address and port at both ends means the more
    specific binding swallows the reply, and the test passes for the wrong
    reason -- which is exactly what happened the first time this was written.
    """
    import threading

    ready = threading.Event()

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.2", 0))
        probe.close()
    except OSError:
        pytest.skip("this host cannot bind 127.0.0.2")

    def serve():
        from scapy.contrib.automotive.someip import SD, SDEntry_Service, SDOption_IP4_EndPoint, SOMEIP

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.2", sd_port))
        sock.settimeout(5.0)
        ready.set()
        try:
            _, peer = sock.recvfrom(65535)
        except (TimeoutError, socket.timeout):
            sock.close()
            return
        entry = SDEntry_Service(
            type=0x01, srv_id=0x4321, inst_id=7, major_ver=1, minor_ver=0, ttl=5, n_opt_1=1
        )
        option = SDOption_IP4_EndPoint(addr="127.0.0.2", l4_proto=6, port=30509)
        sock.sendto(bytes(SOMEIP() / SD(entry_array=[entry], option_array=[option])), peer)
        sock.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(3), "responder did not start"
    return sd_port


@pytest.mark.integration
def test_find_gets_an_answer_over_unicast(responder):
    """The reason find() exists: no multicast anywhere in this path.

    Across a router or a VPN the group is not forwarded, so a passive listen
    reports 'no services' about a bus full of them.
    """
    offers = ServiceDiscovery(
        SdConfig(group=GROUP, port=responder)
    ).find(host="127.0.0.2", timeout=2.0)

    assert [o.canonical_id for o in offers] == ["4321:0007"]
    assert offers[0].endpoints == [("127.0.0.2", 30509, "tcp")]


@pytest.mark.integration
def test_find_sends_a_wildcard_findservice_entry(responder):
    """What goes on the wire must be a FindService for any service, any instance."""
    from scapy.contrib.automotive.someip import SD, SOMEIP

    datagram = ServiceDiscovery._find_datagram(0xFFFF, 0xFFFF, ttl=3)
    entry = SD(bytes(SOMEIP(datagram).payload)).entry_array[0]

    assert int(entry.type) == 0x00
    assert (int(entry.srv_id), int(entry.inst_id)) == (0xFFFF, 0xFFFF)


@pytest.mark.integration
def test_a_host_that_never_answers_returns_nothing(sd_port):
    offers = ServiceDiscovery(SdConfig(group=GROUP, port=sd_port)).find(
        host="127.0.0.3", timeout=0.5
    )

    assert offers == []


@pytest.mark.integration
def test_joining_on_an_interface_this_host_lacks_says_what_it_has(sd_port):
    """The kernel answers ENODEV, which sends people looking at the ECU.

    192.0.2.1 is TEST-NET-1: routable-looking, never a local address.
    """
    discovery = ServiceDiscovery(SdConfig(group=GROUP, interface="192.0.2.1", port=sd_port))

    with pytest.raises(NotConfigured) as exc:
        discovery.listen(timeout=0.2)

    message = str(exc.value)
    assert "must name a NIC on this host" in message
    assert "Available here" in message


def test_no_interface_means_let_the_kernel_choose():
    address = ServiceDiscovery(SdConfig(group=GROUP))._interface_address()

    assert address == struct.pack("=I", socket.INADDR_ANY)
