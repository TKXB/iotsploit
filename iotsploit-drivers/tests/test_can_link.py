"""Interface properties must be read from the kernel, never assumed.

The driver used to attach bitrate 500000 to every interface it discovered and
then apply it, which replaced a working CAN FD configuration with a wrong one.
These tests pin the parsing that replaced the assumption, against recorded
``ip -details link show`` output. Nothing here touches a device.
"""

import subprocess

import pytest

from iotsploit_drivers.socketcan.can_link import CanLinkInfo, parse_ip_link_details, read_can_links

pytestmark = pytest.mark.unit

# A CAN FD interface that is up and error-passive, a classic one that is down,
# a vcan, and two non-CAN devices that must not be mistaken for interfaces.
IP_OUTPUT = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00 promiscuity 0
2: canyon0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether dc:a6:32:11:22:33 brd ff:ff:ff:ff:ff:ff
3: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 72 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can  promiscuity 0 minmtu 0 maxmtu 0
    can state ERROR-PASSIVE (berr-counter tx 0 rx 136) restart-ms 0
\t  bitrate 500000 sample-point 0.875
\t  tq 50 prop-seg 6 phase-seg1 7 phase-seg2 2 sjw 1 brp 1
\t  dbitrate 2000000 dsample-point 0.750
\t  pcan_usb_fd: tseg1 1..256 tseg2 1..128 sjw 1..128 brp 1..1024 brp_inc 1
\t  pcan_usb_fd: dtseg1 1..32 dtseg2 1..16 dsjw 1..16 dbrp 1..1024 dbrp_inc 1
\t  clock 80000000 numtxqueues 1 numrxqueues 1
4: can1: <NOARP,ECHO> mtu 16 qdisc pfifo_fast state DOWN mode DEFAULT group default qlen 10
    link/can  promiscuity 0
    can state STOPPED restart-ms 0
5: vcan0: <NOARP,UP,LOWER_UP> mtu 72 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can
"""


def test_only_can_interfaces_are_returned():
    links = parse_ip_link_details(IP_OUTPUT)

    # canyon0 contains "can" and is ethernet; the old substring match took it.
    assert sorted(links) == ["can0", "can1", "vcan0"]


def test_an_fd_interface_reports_both_bitrates_and_its_state():
    can0 = parse_ip_link_details(IP_OUTPUT)["can0"]

    assert can0.bitrate == 500000
    # "dbitrate" must not be read as another "bitrate".
    assert can0.dbitrate == 2000000
    assert can0.supports_fd is True
    assert can0.is_up is True
    assert can0.controller_state == "ERROR-PASSIVE"
    assert can0.is_virtual is False


def test_the_controller_behind_an_interface_is_read_from_its_bit_timing_block():
    """The only place ip(8) names the hardware; it is how a PEAK adapter is found."""
    links = parse_ip_link_details(IP_OUTPUT)

    assert links["can0"].timing_const == "pcan_usb_fd"
    # can1 is a CAN interface whose controller reported nothing, and vcan has none.
    assert links["can1"].timing_const is None
    assert links["vcan0"].timing_const is None


def test_a_down_classic_interface_is_reported_as_such():
    can1 = parse_ip_link_details(IP_OUTPUT)["can1"]

    assert can1.is_up is False
    assert can1.supports_fd is False
    assert can1.bitrate is None


def test_a_virtual_interface_is_flagged_and_has_no_bitrate():
    vcan0 = parse_ip_link_details(IP_OUTPUT)["vcan0"]

    assert vcan0.is_virtual is True
    assert vcan0.bitrate is None
    assert vcan0.is_up is True


def test_unknown_bitrate_is_none_rather_than_a_plausible_default():
    # The whole point: absent configuration must read as absent.
    info = parse_ip_link_details(IP_OUTPUT)["vcan0"]

    assert info.bitrate is None
    assert "500000" not in info.describe()


def test_empty_output_yields_no_interfaces():
    assert parse_ip_link_details("") == {}


def test_a_failing_ip_command_reports_nothing_instead_of_raising():
    def failing(_args, **_kwargs):
        return subprocess.CompletedProcess(_args, returncode=1, stdout="", stderr="ip: not found")

    assert read_can_links(runner=failing) == {}


def test_an_unavailable_ip_binary_reports_nothing_instead_of_raising():
    def missing(_args, **_kwargs):
        raise FileNotFoundError("ip")

    assert read_can_links(runner=missing) == {}


def test_describe_names_the_configuration_an_operator_would_check():
    described = CanLinkInfo(name="can0", is_up=True, mtu=72, bitrate=500000, dbitrate=2000000).describe()

    assert described == "can0, up, 500000 bit/s, data 2000000 bit/s, FD"
