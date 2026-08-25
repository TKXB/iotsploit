"""The one-shot SocketCAN sender: what reaches the wire, and what closes after.

Every test here drives a fake bus. Nothing in the deterministic suite may open
can0, vcan0, or a socket of any kind -- a test that transmits is a test that
changes a vehicle.

The invariants worth stating, because each one is a way real hardware gets hurt
or a bug gets hidden:

* the flags come from the frame, so an extended id is not sent as standard;
* ``check=True`` reaches python-can, so a mismatched id or length is refused
  locally rather than truncated on the wire;
* the socket is shut down on every exit path, including the failing one;
* nothing here configures an interface, so a channel that is down is an error
  and never something this code fixes by itself.
"""

from __future__ import annotations

import pytest

from iotsploit_protocols.canbus.definitions import EncodedFrame
from iotsploit_protocols.canbus.socketcan import (
    CanTransportError,
    CaptureBudget,
    SocketCanClient,
    SocketCanConfig,
    SocketCanReceiver,
    list_can_interfaces,
)
from iotsploit_protocols.errors import NotConfigured

pytestmark = pytest.mark.unit


class FakeBus:
    """Records what it was asked to send, and whether it was closed."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sent = []
        self.shutdown_calls = 0
        self.raise_on_send = None

    def send(self, message, timeout=None):
        self.sent.append((message, timeout))
        if self.raise_on_send:
            raise self.raise_on_send

    def shutdown(self):
        self.shutdown_calls += 1


@pytest.fixture
def bus_holder():
    made = []

    def factory(**kwargs):
        bus = FakeBus(**kwargs)
        made.append(bus)
        return bus

    factory.made = made
    return factory


def classic_frame():
    return EncodedFrame(
        frame_id=0x123,
        is_extended=False,
        is_fd=False,
        dlc=8,
        data=bytes.fromhex("A9010E0000000000"),
        name="VehicleStatus",
    )


def extended_fd_frame():
    return EncodedFrame(
        frame_id=0x1ABCDEF,
        is_extended=True,
        is_fd=True,
        dlc=16,
        data=bytes(16),
        name="DiagnosticBlock",
    )


# ── the channel name ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "channel",
    ["", "   ", "can 0", "a" * 16, "../../etc/passwd", "can0\n", None, 5],
)
def test_an_unusable_channel_name_fails_before_any_bus_is_built(channel):
    """python-can reports a bad name as a generic OSError, which reads as "the
    bus is down" rather than "that is not a name"."""
    with pytest.raises(NotConfigured):
        SocketCanConfig(channel=channel)


@pytest.mark.parametrize("channel", ["can0", "vcan0", "can_pcan1", "slcan0"])
def test_ordinary_interface_names_are_accepted(channel):
    assert SocketCanConfig(channel=channel).channel == channel


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_non_positive_timeout_is_refused(timeout):
    with pytest.raises(NotConfigured, match="timeout"):
        SocketCanConfig(channel="can0", timeout=timeout)


# ── what reaches the bus ──────────────────────────────────────────────


def test_the_bus_is_opened_on_the_named_channel_without_host_config(bus_holder):
    """ignore_config keeps a host can.conf from redirecting this to another
    interface or quietly supplying a bitrate."""
    with SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder):
        pass

    kwargs = bus_holder.made[0].kwargs
    assert kwargs["interface"] == "socketcan"
    assert kwargs["channel"] == "can0"
    assert kwargs["ignore_config"] is True


def test_no_bitrate_or_link_state_is_ever_passed(bus_holder):
    """Interface setup is host configuration. A tool that reconfigures a bus to
    make its own call succeed has changed the vehicle to suit itself."""
    with SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder) as client:
        client.send(classic_frame())

    assert set(bus_holder.made[0].kwargs) == {"interface", "channel", "fd", "ignore_config"}


def test_a_classic_frame_carries_its_own_flags(bus_holder):
    with SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder) as client:
        client.send(classic_frame())

    message, _ = bus_holder.made[0].sent[0]
    assert message.arbitration_id == 0x123
    assert message.is_extended_id is False
    assert message.is_fd is False
    assert bytes(message.data).hex().upper() == "A9010E0000000000"


def test_an_extended_fd_frame_carries_its_own_flags(bus_holder):
    """python-can defaults is_extended_id to True, so a standard frame sent
    without setting it explicitly goes out as extended."""
    frame = extended_fd_frame()

    with SocketCanClient(SocketCanConfig("can0", fd=True), bus_factory=bus_holder) as client:
        client.send(frame)

    message, _ = bus_holder.made[0].sent[0]
    assert message.arbitration_id == 0x1ABCDEF
    assert message.is_extended_id is True
    assert message.is_fd is True
    assert len(message.data) == 16


def test_the_socket_is_opened_in_fd_mode_only_for_an_fd_frame(bus_holder):
    """A classic socket rejects a 16-byte payload."""
    with SocketCanClient(SocketCanConfig("can0", fd=True), bus_factory=bus_holder):
        pass
    with SocketCanClient(SocketCanConfig("can0", fd=False), bus_factory=bus_holder):
        pass

    assert bus_holder.made[0].kwargs["fd"] is True
    assert bus_holder.made[1].kwargs["fd"] is False


def test_the_configured_timeout_reaches_the_send(bus_holder):
    with SocketCanClient(SocketCanConfig("can0", timeout=2.5), bus_factory=bus_holder) as client:
        client.send(classic_frame())

    assert bus_holder.made[0].sent[0][1] == 2.5


def test_an_impossible_frame_is_refused_locally(bus_holder):
    """check=True is what makes python-can validate the id against the flag
    before anything reaches the kernel."""
    too_wide = EncodedFrame(
        frame_id=0x9999, is_extended=False, is_fd=False, dlc=1, data=b"\x00", name="Bad"
    )

    with pytest.raises(CanTransportError):
        with SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder) as client:
            client.send(too_wide)

    assert bus_holder.made == [] or bus_holder.made[0].sent == []


def test_one_send_puts_exactly_one_frame_on_the_wire(bus_holder):
    """No retry, no repetition. A retry around a send that may already have
    reached an ECU turns one confirmed action into several unconfirmed ones."""
    with SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder) as client:
        client.send(classic_frame())

    assert len(bus_holder.made[0].sent) == 1


# ── lifecycle ─────────────────────────────────────────────────────────


def test_the_socket_is_closed_after_a_successful_send(bus_holder):
    with SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder) as client:
        client.send(classic_frame())

    assert bus_holder.made[0].shutdown_calls == 1


def test_the_socket_is_closed_after_a_failed_send(bus_holder):
    """A leaked SocketCAN socket keeps filling a kernel buffer nobody drains."""
    client = SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder)

    with pytest.raises(CanTransportError):
        with client:
            bus_holder.made and None
            client.open()
            bus_holder.made[0].raise_on_send = OSError("ENETDOWN")
            client.send(classic_frame())

    assert bus_holder.made[0].shutdown_calls == 1


def test_a_failure_to_close_does_not_mask_the_result(bus_holder):
    """The send already happened; raising from cleanup would report a failure
    that did not occur."""

    def factory(**kwargs):
        bus = FakeBus(**kwargs)
        bus.shutdown = lambda: (_ for _ in ()).throw(OSError("already gone"))
        return bus

    with SocketCanClient(SocketCanConfig("can0"), bus_factory=factory) as client:
        client.send(classic_frame())


def test_an_interface_that_cannot_be_opened_explains_itself():
    """Not a traceback, and not a claim that the frame failed to send: it never
    got as far as a socket."""

    def factory(**kwargs):
        raise OSError(19, "No such device")

    with pytest.raises(CanTransportError, match="has to exist and be up"):
        SocketCanClient(SocketCanConfig("can0"), bus_factory=factory).open()


def test_closing_twice_is_harmless(bus_holder):
    client = SocketCanClient(SocketCanConfig("can0"), bus_factory=bus_holder)
    client.open()

    client.close()
    client.close()

    assert bus_holder.made[0].shutdown_calls == 1


# ── the bounded receiver ──────────────────────────────────────────────


class FakeClock:
    """Advances only when the test says so, so a budget test takes no time."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ReceivingBus(FakeBus):
    def __init__(self, script=(), clock=None, tick=0.0, **kwargs):
        super().__init__(**kwargs)
        self.script = list(script)
        self.recv_calls = 0
        self.timeouts = []
        self._clock = clock
        self._tick = tick

    def recv(self, timeout=None):
        self.recv_calls += 1
        self.timeouts.append(timeout)
        if self._clock is not None:
            self._clock.advance(self._tick)
        return self.script.pop(0) if self.script else None


def receiver_over(script, clock=None, tick=0.01, **config):
    """A receiver whose clock advances on every recv.

    Time has to move even when the bus is silent, or a deadline that a real
    monotonic clock would reach never arrives and the test hangs rather than
    fails. `tick` is how long each recv is pretended to take.
    """
    clock = clock or FakeClock()
    made = []

    def factory(**kwargs):
        bus = ReceivingBus(script=script, clock=clock, tick=tick, **kwargs)
        made.append(bus)
        return bus

    receiver = SocketCanReceiver(
        SocketCanConfig(channel=config.pop("channel", "can0"), **config),
        bus_factory=factory,
        clock=clock,
    )
    return receiver, made


@pytest.mark.parametrize("duration, frames", [(0, 10), (-1, 10), (5, 0), (5, -1)])
def test_a_budget_must_be_positive(duration, frames):
    """A capture with no budget is a leak: it runs in a worker, and an
    observation scope needs a run that ends."""
    with pytest.raises(NotConfigured):
        CaptureBudget(duration_s=duration, max_frames=frames)


def test_the_frame_budget_ends_the_capture():
    receiver, made = receiver_over(["a", "b", "c", "d", "e"])

    received = list(receiver.frames(CaptureBudget(duration_s=60, max_frames=3)))

    assert received == ["a", "b", "c"]
    assert made[0].shutdown_calls == 1


def test_the_duration_budget_ends_the_capture_on_a_busy_bus():
    """Neither budget is redundant: this one saves you when frames never stop."""
    clock = FakeClock()
    receiver, made = receiver_over(["x"] * 1000, clock=clock, tick=0.1)

    received = list(receiver.frames(CaptureBudget(duration_s=1.0, max_frames=10_000)))

    assert 0 < len(received) < 1000
    assert made[0].shutdown_calls == 1


def test_a_silent_bus_still_reaches_its_deadline():
    """recv returns None on timeout. A loop that only checked the clock after a
    frame would block past its deadline on a bus with no traffic at all."""
    clock = FakeClock()
    receiver, made = receiver_over([], clock=clock, tick=0.25)

    received = list(receiver.frames(CaptureBudget(duration_s=1.0, max_frames=100)))

    assert received == []
    assert made[0].shutdown_calls == 1


def test_the_recv_timeout_never_overshoots_the_deadline():
    """Otherwise a 30s recv timeout on a 1s capture blocks 29s past the end."""
    clock = FakeClock()
    receiver, made = receiver_over([], clock=clock, tick=0.25)

    list(receiver.frames(CaptureBudget(duration_s=0.1, max_frames=10)))

    assert made[0].timeouts
    assert all(t <= 0.1 for t in made[0].timeouts)


def test_stopping_early_ends_the_capture():
    receiver, made = receiver_over(["a", "b", "c"])
    receiver.stop()

    assert list(receiver.frames(CaptureBudget(duration_s=60, max_frames=100))) == []
    assert made[0].shutdown_calls == 1


def test_abandoning_the_generator_still_closes_the_socket():
    """A leaked SocketCAN socket keeps filling a kernel buffer nobody drains."""
    receiver, made = receiver_over(["a", "b", "c", "d"])

    stream = receiver.frames(CaptureBudget(duration_s=60, max_frames=100))
    next(stream)
    stream.close()

    assert made[0].shutdown_calls == 1


def test_an_exception_mid_capture_still_closes_the_socket():
    class Exploding(FakeBus):
        def recv(self, timeout=None):
            raise RuntimeError("driver fell over")

    made = []

    def factory(**kwargs):
        bus = Exploding(**kwargs)
        made.append(bus)
        return bus

    receiver = SocketCanReceiver(SocketCanConfig("can0"), bus_factory=factory)

    with pytest.raises(RuntimeError):
        list(receiver.frames(CaptureBudget(duration_s=1, max_frames=10)))

    assert made[0].shutdown_calls == 1


def test_the_receiver_has_no_send_path():
    """Not a disabled one, not a private one. What it cannot do is part of what
    it is."""
    assert not hasattr(SocketCanReceiver, "send")


def test_the_receiver_never_configures_the_link():
    receiver, made = receiver_over([])

    list(receiver.frames(CaptureBudget(duration_s=0.01, max_frames=1)))

    assert set(made[0].kwargs) == {"interface", "channel", "fd", "ignore_config"}
    assert made[0].kwargs["ignore_config"] is True


# ── listing what the host has ─────────────────────────────────────────


def write_interface(root, name, type_id, operstate="up"):
    entry = root / name
    entry.mkdir()
    (entry / "type").write_text(f"{type_id}\n")
    (entry / "operstate").write_text(f"{operstate}\n")
    return entry


def test_only_can_interfaces_are_listed(tmp_path):
    """ARPHRD_CAN is 280. Ethernet is 1, loopback 772, and a list that included
    them would offer an operator a channel that cannot carry a CAN frame."""
    write_interface(tmp_path, "eth0", 1)
    write_interface(tmp_path, "lo", 772)
    write_interface(tmp_path, "can0", 280)

    found = list_can_interfaces(str(tmp_path))

    assert [i.name for i in found] == ["can0"]


def test_a_virtual_interface_is_marked_as_one(tmp_path):
    """vcan carries no transceiver, so nothing done on it reaches a vehicle --
    which is worth saying before a capture, not after."""
    write_interface(tmp_path, "can0", 280)
    write_interface(tmp_path, "vcan0", 280)

    found = {i.name: i for i in list_can_interfaces(str(tmp_path))}

    assert found["vcan0"].is_virtual is True
    assert found["can0"].is_virtual is False


def test_a_down_interface_is_listed_as_down_not_hidden(tmp_path):
    """Hiding it leaves the operator wondering why the interface they can see
    in `ip link` is absent here."""
    write_interface(tmp_path, "can0", 280, operstate="down")

    found = list_can_interfaces(str(tmp_path))

    assert found[0].is_up is False
    assert "down" in found[0].label


def test_an_unknown_operstate_counts_as_usable(tmp_path):
    """vcan reports "unknown" rather than "up". Treating that as down would
    hide the one interface that is safe to practise on."""
    write_interface(tmp_path, "vcan0", 280, operstate="unknown")

    assert list_can_interfaces(str(tmp_path))[0].is_up is True


def test_an_unreadable_entry_is_skipped_not_fatal(tmp_path):
    """sysfs entries come and go as devices are plugged in."""
    write_interface(tmp_path, "can0", 280)
    (tmp_path / "half_made").mkdir()

    assert [i.name for i in list_can_interfaces(str(tmp_path))] == ["can0"]


def test_a_missing_sysfs_root_returns_nothing(tmp_path):
    """Not every host has CAN, and none of them should get a traceback."""
    assert list_can_interfaces(str(tmp_path / "nope")) == []
