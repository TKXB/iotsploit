"""One-shot SocketCAN I/O: open, do exactly one thing, close.

This is deliberately not a driver. ``iotsploit_drivers.socketcan`` owns
discovery, link lifecycle, and a long-lived streaming socket, and it stays that
way -- borrowing it here would either drag privileged link mutation into a send
path or add a second mutable "current device" to race against. SocketCAN allows
several sockets on one interface, so a client here and the driver's monitor
coexist without contending for the bus.

Two prohibitions are absolute, and they are why this module is small:

*It never changes host networking.* No ``sudo``, no ``ip link``, no bitrate, no
listen-only, no bringing an interface up. A link is configured outside
IoTSploit; this opens one that is already up or fails saying so. A tool that
quietly reconfigures an interface to make its own call succeed has changed the
vehicle's bus to suit itself.

*It never retries.* One request puts at most one frame on the wire. A retry
loop around a send that may have already reached an ECU is how one confirmed
action becomes several unconfirmed ones.

``python-can`` is imported inside the functions that need it, not at module
scope. It opens platform sockets and reads host configuration on import, and a
preview must work on a host with no CAN interface at all.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from iotsploit_protocols.canbus.definitions import EncodedFrame
from iotsploit_protocols.errors import NotConfigured, ProtocolError

#: Linux caps an interface name at IFNAMSIZ-1 and forbids whitespace and '/'.
#: Checked before opening because python-can reports a bad name as a generic
#: OSError, which reads as "the bus is down" rather than "that is not a name".
#: ``\Z`` rather than ``$``: ``$`` also matches just before a trailing
#: newline, so "can0\n" would pass as a valid name.
_CHANNEL_RE = re.compile(r"\A[A-Za-z0-9_.:-]{1,15}\Z")

#: What builds the underlying bus. Injected in tests so the deterministic suite
#: never opens can0, vcan0, or a socket of any kind.
BusFactory = Callable[..., Any]


class CanTransportError(ProtocolError):
    """The local socket refused the frame.

    Never means an ECU did or did not receive anything. It means this host's
    CAN stack would not accept the message for transmission, which is a
    different claim entirely and is the only one a sender can honestly make.
    """


@dataclass(frozen=True)
class SocketCanConfig:
    """Where to send, and how long to wait for the socket to take it.

    ``channel`` is the kernel interface name (``can0``), never the device
    driver's own id (``can_001``). They look similar in a UI and only one of
    them can be opened.
    """

    channel: str
    timeout: float = 1.0
    #: Whether to open the socket in FD mode. Set from the frame, not guessed:
    #: a classic socket rejects a 16-byte payload.
    fd: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.channel, str) or not _CHANNEL_RE.match(self.channel):
            raise NotConfigured(
                f"{self.channel!r} is not a usable SocketCAN interface name; "
                "expected something like 'can0' or 'vcan0'"
            )
        if self.timeout is None or self.timeout <= 0:
            raise NotConfigured(f"send timeout must be positive, not {self.timeout!r}")


def _default_bus_factory(**kwargs: Any) -> Any:
    import can  # imported here: see the module docstring

    return can.Bus(**kwargs)


def _build_message(frame: EncodedFrame) -> Any:
    import can

    return can.Message(
        arbitration_id=frame.frame_id,
        is_extended_id=frame.is_extended,
        is_fd=frame.is_fd,
        data=frame.data,
        # check=True makes python-can validate the id against the flag and the
        # payload length against the frame type before anything reaches the
        # kernel, so a mismatch is a stated error rather than a silent
        # truncation on the wire.
        check=True,
    )


class SocketCanClient:
    """A socket that exists for the duration of one send.

    Used as a context manager so the socket closes on every path, including the
    one where the send raised. A leaked SocketCAN socket keeps receiving into a
    kernel buffer nobody drains.
    """

    def __init__(
        self,
        config: SocketCanConfig,
        *,
        bus_factory: Optional[BusFactory] = None,
    ) -> None:
        self.config = config
        self._bus_factory = bus_factory or _default_bus_factory
        self._bus: Any = None

    def __enter__(self) -> "SocketCanClient":
        self.open()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def open(self) -> None:
        if self._bus is not None:
            return
        try:
            self._bus = self._bus_factory(
                interface="socketcan",
                channel=self.config.channel,
                fd=self.config.fd,
                # The host's can.conf must not be able to redirect this to
                # another interface or quietly supply a bitrate.
                ignore_config=True,
            )
        except Exception as error:
            raise CanTransportError(
                f"cannot open SocketCAN interface {self.config.channel!r}: {error}. "
                "The interface has to exist and be up before sending; "
                "IoTSploit does not configure it."
            ) from error

    def close(self) -> None:
        bus, self._bus = self._bus, None
        if bus is None:
            return
        try:
            bus.shutdown()
        except Exception:  # noqa: BLE001 - a failed close must not mask the result
            pass

    def send(self, frame: EncodedFrame) -> None:
        """Put exactly one frame on the wire.

        Returning normally means the local socket accepted the frame. It does
        not mean an ECU received it, acted on it, or even that anything was
        listening -- and no caller may report otherwise.
        """
        if self._bus is None:
            self.open()

        try:
            message = _build_message(frame)
        except (ValueError, TypeError) as error:
            # check=True validates the id against the extended flag and the
            # payload length against the frame type. It raises from the
            # constructor rather than from send(), so catching only around the
            # send would let this escape as a bare ValueError.
            raise CanTransportError(
                f"frame 0x{frame.frame_id:X} cannot be represented on a CAN bus: {error}"
            ) from error

        try:
            self._bus.send(message, timeout=self.config.timeout)
        except Exception as error:
            raise CanTransportError(
                f"SocketCAN refused frame 0x{frame.frame_id:X} on "
                f"{self.config.channel!r}: {error}"
            ) from error


@dataclass(frozen=True)
class CaptureBudget:
    """When a capture stops, stated two ways because either can run out first.

    A capture with no budget is a leak: it runs inside a worker, and an
    observation scope needs a run that ends in order to mean anything. The
    frame budget is the one that saves you on a busy bus, where thirty seconds
    is millions of frames; the duration is the one that saves you on a silent
    bus, where the frame budget would never be reached.
    """

    duration_s: float = 30.0
    max_frames: int = 200_000

    def __post_init__(self) -> None:
        if self.duration_s <= 0:
            raise NotConfigured(f"capture duration must be positive, not {self.duration_s!r}")
        if self.max_frames <= 0:
            raise NotConfigured(f"frame budget must be positive, not {self.max_frames!r}")


class SocketCanReceiver:
    """A read-only socket that yields frames until its budget runs out.

    There is no send path here, not even a disabled one. What this cannot do is
    part of what it is.

    It opens its own socket rather than borrowing the streaming driver's. That
    is not duplication for its own sake: SocketCAN permits several sockets on
    one interface, so a capture neither disturbs nor depends on the driver's
    monitor, and neither one's lifetime is tied to the other's.

    Note for anyone reading this next to the hardware: a CAN controller in
    normal mode **acknowledges frames it receives, in silicon**. Attaching an
    interface to a live bus is therefore not electrically inert, whatever this
    software does or does not send. Listen-only is host link configuration
    (``ip link set can0 type can listen-only on``) and this class must not set
    it, for the same reason the sender must not set a bitrate.
    """

    def __init__(
        self,
        config: SocketCanConfig,
        *,
        bus_factory: Optional[BusFactory] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.config = config
        self._bus_factory = bus_factory or _default_bus_factory
        self._clock = clock or time.monotonic
        self._bus: Any = None
        self._stop = False

    def __enter__(self) -> "SocketCanReceiver":
        self.open()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def open(self) -> None:
        if self._bus is not None:
            return
        try:
            self._bus = self._bus_factory(
                interface="socketcan",
                channel=self.config.channel,
                fd=self.config.fd,
                ignore_config=True,
            )
        except Exception as error:
            raise CanTransportError(
                f"cannot open SocketCAN interface {self.config.channel!r} for capture: "
                f"{error}. The interface has to exist and be up; IoTSploit does not "
                "configure it."
            ) from error

    def close(self) -> None:
        bus, self._bus = self._bus, None
        if bus is None:
            return
        try:
            bus.shutdown()
        except Exception:  # noqa: BLE001 - a failed close must not mask the capture
            pass

    def stop(self) -> None:
        """Ask the loop to finish at its next opportunity."""
        self._stop = True

    def frames(self, budget: CaptureBudget) -> Iterator[Any]:
        """Yield received messages until the budget is spent.

        The socket is closed on every exit path -- normal end, exception, and
        the consumer abandoning the generator -- because a leaked SocketCAN
        socket keeps filling a kernel buffer that nobody drains.
        """
        if self._bus is None:
            self.open()

        started = self._clock()
        deadline = started + budget.duration_s
        delivered = 0
        try:
            while not self._stop and delivered < budget.max_frames:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                # Bounded by whichever is sooner, so a silent bus still wakes up
                # to notice its own deadline instead of blocking past it.
                message = self._bus.recv(timeout=min(remaining, 0.25))
                if message is None:
                    continue
                delivered += 1
                yield message
        finally:
            self.close()


#: ``ARPHRD_CAN`` from ``linux/if_arp.h``. What marks a net device as a CAN
#: interface rather than an Ethernet one.
ARPHRD_CAN = 280


@dataclass(frozen=True)
class CanInterface:
    """A CAN interface this host has, as sysfs describes it."""

    name: str
    is_up: bool
    #: ``vcan``/``vxcan`` devices carry no transceiver, so nothing an operator
    #: does on one can reach a vehicle. Worth saying out loud before a capture.
    is_virtual: bool

    @property
    def label(self) -> str:
        state = "up" if self.is_up else "down"
        kind = "virtual" if self.is_virtual else "hardware"
        return f"{self.name} ({kind}, {state})"


def list_can_interfaces(sysfs_root: str = "/sys/class/net") -> "list[CanInterface]":
    """Every CAN interface on this host, newest kernel truth, read-only.

    Reads sysfs rather than shelling out to ``ip`` or asking the device driver.
    That keeps it unprivileged, keeps it free of the driver's lifecycle -- the
    plugins must not initialize or connect a device merely to list one -- and
    means it works when the driver has never been touched.

    An interface that is *down* is still listed. Hiding it would leave an
    operator wondering why the interface they can see in ``ip link`` is absent
    here; saying "down" tells them what to fix.
    """
    root = Path(sysfs_root)
    found: list[CanInterface] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return found

    for entry in entries:
        try:
            if int((entry / "type").read_text().strip()) != ARPHRD_CAN:
                continue
            operstate = (entry / "operstate").read_text().strip()
        except (OSError, ValueError):
            continue
        found.append(
            CanInterface(
                name=entry.name,
                # vcan reports "unknown" rather than "up"; treat anything that
                # is not explicitly "down" as usable and let the open fail
                # honestly if it is not.
                is_up=operstate != "down",
                is_virtual=entry.name.startswith(("vcan", "vxcan")),
            )
        )
    return found
