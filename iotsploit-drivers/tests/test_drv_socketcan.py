"""The SocketCAN driver must not fabricate traffic or reconfigure a link.

Two invariants, both learned from a bench Pi on a live CAN FD bus:

* a received error frame is bus health, never a CAN message. Reading
  ``arbitration_id`` on one yields an error class, so a driver that skips the
  ``is_error_frame`` check publishes a frame 0x004 that no ECU sent;
* bitrate, FD mode, and link state belong to the operator. The driver reads
  them and may bring up only what it can be told to; it never invents a value
  and never takes down a link it did not raise.

No test here opens a socket or a real interface.
"""

import subprocess

import can
import pytest

from iotsploit_core.domain.device import SocketCANDevice
from iotsploit_core.core.stream_manager import StreamAction
from iotsploit_drivers.socketcan import drv_socketcan
from iotsploit_drivers.socketcan.can_link import CanLinkInfo
from iotsploit_drivers.socketcan.drv_socketcan import SocketCANDriver

pytestmark = pytest.mark.unit


class RecordingStream:
    """Stands in for the websocket fan-out; records what was published."""

    def __init__(self):
        self.published = []

    def broadcast_data(self, stream_data):
        self.published.append(stream_data)

    @property
    def actions(self):
        return [item.action for item in self.published]


class RecordingBus:
    """Stands in for python-can's Bus; records what was sent."""

    def __init__(self):
        self.sent = []
        self.is_shutdown = False

    def send(self, message):
        self.sent.append(message)

    def shutdown(self):
        self.is_shutdown = True


@pytest.fixture
def driver():
    instance = SocketCANDriver()
    instance.stream_wrapper = RecordingStream()
    instance.current_interface = "can0"
    instance.device = SocketCANDevice(
        device_id="can_001",
        name="SocketCAN_can0",
        interface="can0",
        attributes={"supports_fd": True},
    )
    return instance


def error_frame(payload: str, arbitration_id: int = 0x004) -> can.Message:
    return can.Message(
        arbitration_id=arbitration_id,
        data=bytes.fromhex(payload),
        is_error_frame=True,
        timestamp=1.0,
    )


def test_an_error_frame_is_never_published_as_a_can_message(driver):
    driver.handle_received_message(error_frame("0004000000000000"))

    published = driver.stream_wrapper.published
    assert [item.action for item in published] == [StreamAction.ERROR]
    assert published[0].data["kind"] == "bus_error"
    assert published[0].data["description"] == "controller-problem{rx-error-warning}"
    # The bug this replaces: 0x004 appearing as a frame id in the traffic view.
    assert "id" not in published[0].data


def test_error_frames_are_tallied_by_description(driver):
    driver.handle_received_message(error_frame("0004000000000000"))
    driver.handle_received_message(error_frame("0004000000000000"))
    driver.handle_received_message(error_frame("0010000000000000"))

    assert driver.status()["bus_errors"] == {
        "controller-problem{rx-error-warning}": 2,
        "controller-problem{rx-error-passive}": 1,
    }


def test_a_repeated_error_is_rate_limited_but_still_counted(driver):
    driver.handle_received_message(error_frame("0004000000000000"))
    for _ in range(50):
        driver.handle_received_message(error_frame("0004000000000000"))

    # One report for the burst, not fifty-one.
    assert len(driver.stream_wrapper.published) == 1
    assert driver.status()["bus_errors"]["controller-problem{rx-error-warning}"] == 51


def test_a_newly_seen_error_is_reported_immediately(driver):
    driver.handle_received_message(error_frame("0004000000000000"))
    driver.handle_received_message(error_frame("0010000000000000"))

    descriptions = [item.data["description"] for item in driver.stream_wrapper.published]
    assert descriptions == ["controller-problem{rx-error-warning}", "controller-problem{rx-error-passive}"]


def test_an_oscillating_fault_is_rate_limited_per_description(driver):
    # A controller sitting on the error-passive threshold alternates warning
    # and passive on every frame. Rate limiting on "the description changed"
    # would let every one of these through, which is the flood being avoided.
    for _ in range(40):
        driver.handle_received_message(error_frame("0004000000000000"))
        driver.handle_received_message(error_frame("0010000000000000"))

    assert len(driver.stream_wrapper.published) == 2
    assert driver.status()["bus_errors"] == {
        "controller-problem{rx-error-warning}": 40,
        "controller-problem{rx-error-passive}": 40,
    }


def test_a_data_frame_is_published_with_its_flags(driver):
    driver.handle_received_message(
        can.Message(
            arbitration_id=0x15A,
            data=bytes.fromhex("EC04000000000000"),
            is_extended_id=False,
            is_fd=True,
            timestamp=2.0,
        )
    )

    published = driver.stream_wrapper.published[0]
    assert published.action == StreamAction.DATA
    assert published.data == {"id": "0x15a", "data": "ec04000000000000", "dlc": 8}
    assert published.metadata["is_fd"] is True
    assert published.metadata["is_extended_id"] is False


def test_scan_reports_kernel_values_and_never_a_default_bitrate(driver, monkeypatch):
    monkeypatch.setattr(
        drv_socketcan,
        "read_can_links",
        lambda: {
            "can0": CanLinkInfo(name="can0", is_up=True, mtu=72, bitrate=500000, dbitrate=2000000),
            "vcan0": CanLinkInfo(name="vcan0", is_up=True, mtu=72, is_virtual=True),
        },
    )

    devices = {device.interface: device for device in driver._scan_impl()}

    assert devices["can0"].attributes["bitrate"] == 500000
    assert devices["can0"].attributes["supports_fd"] is True
    # The old scan claimed 500000 here, and the driver then applied it.
    assert devices["vcan0"].attributes["bitrate"] is None
    assert devices["can0"].device_id == "can_001"


def test_initializing_an_up_interface_runs_no_privileged_command(driver, monkeypatch):
    monkeypatch.setattr(
        drv_socketcan,
        "read_can_links",
        lambda: {"can0": CanLinkInfo(name="can0", is_up=True, mtu=72, bitrate=1000000)},
    )
    monkeypatch.setattr(
        drv_socketcan.subprocess,
        "run",
        lambda *a, **k: pytest.fail("an already-configured link must not be touched"),
    )

    assert driver._initialize_impl(driver.device) is True
    assert driver._brought_link_up is False


def test_a_down_interface_without_a_bitrate_says_so_instead_of_guessing(driver, monkeypatch):
    monkeypatch.setattr(
        drv_socketcan,
        "read_can_links",
        lambda: {"can0": CanLinkInfo(name="can0", is_up=False, mtu=16)},
    )
    device = SocketCANDevice(device_id="can_001", name="SocketCAN_can0", interface="can0", attributes={})

    with pytest.raises(RuntimeError, match="no bitrate configured"):
        driver._initialize_impl(device)


def test_a_down_interface_is_brought_up_with_the_configured_bitrate(driver, monkeypatch):
    commands = []
    monkeypatch.setattr(
        drv_socketcan,
        "read_can_links",
        lambda: {"can0": CanLinkInfo(name="can0", is_up=False, mtu=72, bitrate=250000)},
    )
    monkeypatch.setattr(
        drv_socketcan.subprocess,
        "run",
        lambda args, **k: commands.append(args) or subprocess.CompletedProcess(args, 0, "", ""),
    )
    device = SocketCANDevice(device_id="can_001", name="SocketCAN_can0", interface="can0", attributes={})

    driver._initialize_impl(device)

    assert commands[0] == ["sudo", "ip", "link", "set", "can0", "type", "can", "bitrate", "250000"]
    assert commands[1] == ["sudo", "ip", "link", "set", "can0", "up"]
    assert driver._brought_link_up is True


def test_closing_leaves_a_link_the_driver_did_not_raise(driver, monkeypatch):
    monkeypatch.setattr(
        drv_socketcan.subprocess,
        "run",
        lambda *a, **k: pytest.fail("a link configured elsewhere must stay up"),
    )
    driver.bus = RecordingBus()
    driver._brought_link_up = False
    monkeypatch.setattr(driver, "stop_streaming", lambda device: None)

    assert driver._close_impl(driver.device) is True
    assert driver.bus is None


def test_a_failing_privileged_command_raises_instead_of_passing_silently(monkeypatch):
    monkeypatch.setattr(
        drv_socketcan.subprocess,
        "run",
        lambda args, **k: subprocess.CompletedProcess(args, 2, "", "RTNETLINK answers: Device or resource busy"),
    )

    with pytest.raises(RuntimeError, match="Device or resource busy"):
        SocketCANDriver._run_ip(["ip", "link", "set", "can0", "up"])


def test_send_carries_the_requested_flags(driver):
    driver.bus = RecordingBus()

    driver.send_can_message(driver.device, 0x18DAF110, b"\x01\x02", is_extended_id=True, is_fd=True)

    sent = driver.bus.sent[0]
    assert sent.arbitration_id == 0x18DAF110
    # Hardcoded False here made every extended-addressed ECU unreachable.
    assert sent.is_extended_id is True
    assert sent.is_fd is True


@pytest.mark.parametrize("args", [{"id": 0x123}, {"data": "0102"}, {"id": 0x123, "data": ""}])
def test_an_incomplete_send_request_is_refused(driver, args):
    driver.bus = RecordingBus()

    # The original defaulted to 0x123 carrying DEADBEEF, putting an invented
    # frame on a real vehicle bus.
    with pytest.raises(ValueError):
        driver._command_send(driver.device, args)

    assert driver.bus.sent == []


@pytest.mark.parametrize("supports_fd", [True, False])
def test_the_bus_always_receives_fd_frames(driver, monkeypatch, supports_fd):
    opened = {}

    def fake_bus(**kwargs):
        opened.update(kwargs)
        return RecordingBus()

    monkeypatch.setattr(drv_socketcan.can.interface, "Bus", fake_bus)
    driver.device.attributes["supports_fd"] = supports_fd

    driver.setup_bus()

    # Deliberately not conditioned on the link's own MTU: a PEAK PCAN-USB FD
    # reports classic while delivering only FD frames, and a socket opened
    # from that MTU sees the bus errors and none of the traffic.
    assert opened["fd"] is True
    assert opened["channel"] == "can0"
    assert opened["interface"] == "socketcan"
