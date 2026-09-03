"""The PCAN driver must find the adapter, and change a link only when told to.

Three properties, all of them read from the kernel rather than assumed:

* a PEAK adapter is recognised by the bit-timing constants its controller
  reports (``pcan_usb_fd`` on the bench PCAN-USB FD), so the driver never
  offers a vcan or somebody else's CAN card as a PEAK adapter;
* initialize validates and records the adapter but leaves the link exactly as
  it found it -- an operator decides when a bus goes live, because raising a
  link makes the controller ACK on a vehicle;
* ``can-up``/``can-down`` act on the device the command was addressed to. The
  manager resolves that device straight out of the scan and never requires an
  initialize, so a driver that reads ``self.current_interface`` instead
  configures nothing, or worse, the wrong bus.

Nothing here opens a socket, an interface, or the privileged helper.
"""

import pytest

from iotsploit_core.domain.device import SocketCANDevice
from iotsploit_drivers.socketcan import drv_socketcan
from iotsploit_drivers.socketcan.can_link import parse_ip_link_details
from iotsploit_drivers.socketcan.drv_pcan import FD_TIMING, PCANDriver
from iotsploit_drivers.socketcan.drv_socketcan import SocketCANDriver

pytestmark = pytest.mark.unit

# Recorded from the bench Raspberry Pi 5 with a PCAN-USB FD plugged in, before
# anything configured it: the adapter is down, and only its bit-timing block
# says what it is. vcan0 and the vendor's own non-PEAK card must not match.
IP_OUTPUT = """8: can0: <NOARP,ECHO> mtu 16 qdisc noop state DOWN mode DEFAULT group default qlen 10
    link/can  promiscuity 0 allmulti 0 minmtu 0 maxmtu 0
    can state STOPPED (berr-counter tx 0 rx 0) restart-ms 0
\t  pcan_usb_fd: tseg1 1..256 tseg2 1..128 sjw 1..128 brp 1..1024 brp_inc 1
\t  pcan_usb_fd: dtseg1 1..32 dtseg2 1..16 dsjw 1..16 dbrp 1..1024 dbrp_inc 1
\t  clock 80000000 numtxqueues 1 numrxqueues 1
9: can1: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can  promiscuity 0
    can state ERROR-ACTIVE restart-ms 100
\t  bitrate 500000 sample-point 0.875
\t  mcp251x: tseg1 3..16 tseg2 2..8 sjw 1..4 brp 1..64 brp_inc 1
10: vcan0: <NOARP,UP,LOWER_UP> mtu 72 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can
"""

# A rig carrying two PEAK adapters: a link command must act on the one it was
# addressed to, not on whichever was initialized first.
IP_OUTPUT_TWO_ADAPTERS = IP_OUTPUT + """11: can2: <NOARP,ECHO> mtu 16 qdisc noop state DOWN mode DEFAULT group default qlen 10
    link/can  promiscuity 0
    can state STOPPED restart-ms 0
\t  pcan_usb_fd: tseg1 1..256 tseg2 1..128 sjw 1..128 brp 1..1024 brp_inc 1
"""

# The same can0 once ``can-fd-up`` has run: FD on, both bitrates, sampled at 75%.
IP_OUTPUT_CONFIGURED = """8: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 72 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can  promiscuity 0
    can state ERROR-ACTIVE restart-ms 0
\t  bitrate 500000 sample-point 0.750
\t  dbitrate 2000000 dsample-point 0.750
\t  pcan_usb_fd: tseg1 1..256 tseg2 1..128 sjw 1..128 brp 1..1024 brp_inc 1
\t  clock 80000000
"""


class RecordingStream:
    """Stands in for the websocket fan-out; close walks through it."""

    def __init__(self):
        self.published = []

    def broadcast_data(self, stream_data):
        self.published.append(stream_data)

    def register_stream(self, _channel):
        pass

    def unregister_stream(self, _channel):
        pass

    def stop_broadcast(self, _channel):
        pass


class RecordingHelper:
    """Stands in for the privileged helper; records the verbs asked of it."""

    def __init__(self):
        self.calls = []

    def __call__(self, verb, args):
        self.calls.append((verb, args))
        return type("Result", (), {"ok": True, "stderr": ""})()


@pytest.fixture
def helper(monkeypatch):
    recorder = RecordingHelper()
    # The helper is called through the SocketCAN driver, which owns _run_privileged.
    monkeypatch.setattr(drv_socketcan, "privileged_call", recorder)
    return recorder


@pytest.fixture
def links(monkeypatch):
    """Point both drivers at recorded ip(8) output instead of this host."""

    def install(text):
        parsed = parse_ip_link_details(text)
        for module_name in ("iotsploit_drivers.socketcan.drv_pcan", "iotsploit_drivers.socketcan.drv_socketcan"):
            monkeypatch.setattr(f"{module_name}.read_can_links", lambda *_a, **_k: parsed)

    install(IP_OUTPUT)
    return install


@pytest.fixture
def driver(helper, links):
    instance = PCANDriver()
    instance.stream_wrapper = RecordingStream()
    return instance


def can0(driver) -> SocketCANDevice:
    return next(device for device in driver.scan() if device.interface == "can0")


def test_scan_reports_the_peak_adapter_and_nothing_else(driver):
    found = {device.interface: device for device in driver.scan()}

    # can1 is a real CAN interface on an MCP2515, and vcan0 is not hardware.
    assert list(found) == ["can0"]
    assert found["can0"].attributes["timing_const"] == "pcan_usb_fd"
    assert "PEAK" in found["can0"].attributes["description"]


def test_a_peak_adapter_and_a_generic_can_interface_are_not_the_same_device(driver):
    """DeviceStore keys by device_id alone, so the two drivers must not clash."""
    generic = SocketCANDriver()
    generic.stream_wrapper = RecordingStream()

    pcan_ids = {device.device_id for device in driver.scan()}
    socketcan_ids = {device.device_id for device in generic.scan()}

    assert pcan_ids == {"pcan_001"}
    assert not pcan_ids & socketcan_ids


def test_initialize_validates_the_adapter_without_touching_the_link(driver, helper):
    """Plugging an adapter in must not put a controller on somebody's bus."""
    device = can0(driver)

    assert driver.initialize(device) is True
    assert helper.calls == []
    assert device.attributes["is_up"] is False


def test_can_up_applies_the_fd_configuration_in_one_privileged_call(driver, helper, links):
    device = can0(driver)
    links(IP_OUTPUT_CONFIGURED)

    assert "can0 configured" in driver.command(device, "can-up")
    assert helper.calls == [("can-fd-up", {"iface": "can0", **FD_TIMING})]
    # What the driver reports back is what the kernel accepted, not what it asked for.
    assert device.attributes["bitrate"] == 500000
    assert device.attributes["dbitrate"] == 2000000
    assert device.attributes["supports_fd"] is True
    assert device.attributes["is_up"] is True


def test_can_down_lowers_the_link_and_stops_calling_it_up(driver, helper, links):
    device = can0(driver)
    links(IP_OUTPUT_CONFIGURED)
    driver.command(device, "can-up")
    helper.calls.clear()
    links(IP_OUTPUT)

    assert "can0 lowered" in driver.command(device, "can-down")
    assert helper.calls == [("can-link-state", {"iface": "can0", "state": "down"})]
    # The attribute an operator reads must follow the link, not the last request.
    assert device.attributes["is_up"] is False


def test_a_link_command_acts_on_the_device_it_was_addressed_to(driver, helper, links):
    """No initialize, two adapters: the addressed one is the one configured."""
    links(IP_OUTPUT_TWO_ADAPTERS)
    can2 = next(device for device in driver.scan() if device.interface == "can2")

    driver.command(can2, "can-up")

    assert [args["iface"] for _verb, args in helper.calls] == ["can2"]


def test_initialize_refuses_an_interface_that_is_not_a_peak_adapter(driver, helper):
    device = SocketCANDevice(device_id="pcan_002", name="PCAN_can1", interface="can1")

    with pytest.raises(RuntimeError, match="not a PEAK adapter"):
        driver.initialize(device)

    # An interface belonging to another controller is never reconfigured.
    assert helper.calls == []


def test_initialize_refuses_an_interface_that_is_not_on_this_host(driver, helper):
    device = SocketCANDevice(device_id="pcan_009", name="PCAN_can8", interface="can8")

    with pytest.raises(RuntimeError, match="not a CAN interface"):
        driver.initialize(device)

    assert helper.calls == []


def test_close_lowers_a_link_this_driver_raised(driver, helper, links):
    device = can0(driver)
    links(IP_OUTPUT_CONFIGURED)
    driver.command(device, "can-up")
    helper.calls.clear()

    assert driver.close(device) is True
    assert helper.calls == [("can-link-state", {"iface": "can0", "state": "down"})]
    assert driver.current_interface is None


def test_the_applied_timing_is_reported_only_once_it_has_been_applied(driver, links):
    device = can0(driver)

    assert driver.status()["fd_timing"] is None

    links(IP_OUTPUT_CONFIGURED)
    driver.command(device, "can-up")

    assert driver.status()["fd_timing"] == FD_TIMING
    assert driver.status()["owns_link"] is True
