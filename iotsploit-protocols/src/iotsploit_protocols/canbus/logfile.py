"""Read a recorded CAN log back as frames, so a stored capture decodes like a live one.

What this buys is not convenience. A bus you can only watch live is a bus you
can only analyse while you are standing next to the vehicle, and a finding you
cannot replay is a finding nobody else can check. Feeding a file through the
same aggregator, the same codec, and the same target definitions as a live
capture is what makes a recorded window reviewable evidence.

The messages yielded here are deliberately *not* ``can.Message``. Nothing
downstream needs one: :class:`~iotsploit_exploits.canbus.live_capture.CaptureAggregator`
reads identity, payload, arrival time, and the frame-class flags by attribute
and nothing else. ASC stays a small native parser; binary BLF and the two other
widely used text formats delegate parsing to ``python-can`` without ever
constructing a CAN bus or touching a platform socket.

Three things in the Vector ASC format are worth knowing before changing this,
because each one silently produces plausible wrong numbers rather than an
error:

*The ``base`` directive governs identifiers only.* ``base hex`` does not make
DLC and data-length hexadecimal; those columns are decimal in every ASC this
has been checked against. Reading them as hex turns the CAN FD length codes
``10 16``, ``12 24`` and ``13 32`` into 22, 36 and 50 bytes, which truncates
payloads on exactly the frames that carry the most signal.

*DLC is a length code, not a length.* Above eight, CAN FD's DLC indexes a
table (9 to 15 mean 12, 16, 20, 24, 32, 48, 64 bytes). Both columns are present
in the file and they must agree; a line where they do not is a line this reader
did not understand.

*There is more than one CAN FD column order in the wild.* Vector's own writer
puts direction before identifier; other tools emit the classic-CAN order with
identifier first. Both appear in real logs, so both are read here, anchored on
whichever column actually holds ``Rx``/``Tx`` rather than on a fixed offset.

A line this reader cannot parse is counted and skipped, never guessed at and
never fatal. A single corrupt line in the middle of fifty thousand must not end
a replay, and a count of what was skipped is what lets an operator tell a clean
read from a partial one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Type

from iotsploit_protocols.errors import NotConfigured

#: CAN FD data-length codes above 8. ``linux/can.h`` calls this ``can_fd_dlc2len``.
DLC_TO_LENGTH: Dict[int, int] = {
    **{code: code for code in range(9)},
    9: 12,
    10: 16,
    11: 20,
    12: 24,
    13: 32,
    14: 48,
    15: 64,
}

#: Every payload size a CAN or CAN FD frame can actually have.
VALID_LENGTHS = frozenset(DLC_TO_LENGTH.values())

#: Direction columns. ``TxRq`` is a transmit *request*, logged in addition to
#: the ``Tx`` that follows it -- counting both would double every frame this
#: host sent, so it is skipped rather than replayed.
_DIRECTIONS = frozenset({"Rx", "Tx"})
_TX_REQUEST = "TxRq"

#: An identifier column, optionally flagged extended with a trailing ``x``.
_ID_RE = re.compile(r"\A([0-9A-Fa-f]+)(x?)\Z")

#: Header forms this reader understands. Anything else in the header is ignored
#: rather than refused: ASC writers emit tool-specific directives freely, and a
#: replay must not fail because it met one it had not seen.
_DATE_FORMATS = (
    "%a %b %d %I:%M:%S %p %Y",
    "%a %b %d %I:%M:%S.%f %p %Y",
    "%a %b %d %H:%M:%S %Y",
    "%a %b %d %H:%M:%S.%f %Y",
)

MAX_STANDARD_FRAME_ID = 0x7FF
MAX_EXTENDED_FRAME_ID = 0x1FFFFFFF
LogChannel = int | str


class CanLogError(NotConfigured):
    """The log cannot be read, or is not a format this understands.

    A subclass of :class:`NotConfigured` because every case it covers is a
    choice the operator can correct -- a path that is not there, a suffix
    nothing here parses -- rather than a fault in the bus or the target.
    """


@dataclass(frozen=True)
class ReplayMessage:
    """One frame read back from a log.

    The attribute names are ``python-can``'s because that is the shape the
    aggregator reads. The class is a plain dataclass because that is all the
    shape actually requires.
    """

    timestamp: float
    arbitration_id: int
    data: bytes
    is_extended_id: bool = False
    is_error_frame: bool = False
    is_remote_frame: bool = False
    is_fd: bool = False
    channel: Optional[LogChannel] = None

    @property
    def dlc(self) -> int:
        return len(self.data)


@dataclass
class LogReadStats:
    """What a read actually saw, as opposed to what it was asked for.

    Read after iterating. ``unparsable_lines`` is the number that matters: a
    replay reporting 47,797 frames and 0 skipped lines is a clean read of the
    whole file, and the same replay reporting 12,000 skipped lines is a partial
    one wearing the same summary.
    """

    format: str = "asc"
    frames: int = 0
    error_frames: int = 0
    unparsable_lines: int = 0
    channels_present: Set[LogChannel] = field(default_factory=set)
    first_timestamp: Optional[float] = None
    last_timestamp: Optional[float] = None
    #: Wall-clock start from the log's own ``date`` header, when it had one.
    started_at: Optional[datetime] = None
    truncated: bool = False

    @property
    def duration_s(self) -> float:
        if self.first_timestamp is None or self.last_timestamp is None:
            return 0.0
        return round(self.last_timestamp - self.first_timestamp, 6)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "frames": self.frames,
            "error_frames": self.error_frames,
            "unparsable_lines": self.unparsable_lines,
            "channels_present": sorted(self.channels_present, key=channel_sort_key),
            "duration_s": self.duration_s,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "truncated": self.truncated,
        }


def channel_sort_key(channel: LogChannel) -> Tuple[int, str]:
    """Keep numeric channels ordered before named interfaces such as ``can0``."""
    if isinstance(channel, int):
        return 0, f"{channel:020d}"
    return 1, channel


def normalize_log_channel(value: Any) -> Optional[LogChannel]:
    """Normalize an API/CLI channel without losing candump interface names."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("log_channel must be a channel number or interface name")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("log_channel must not be negative")
        return value
    if isinstance(value, str):
        channel = value.strip()
        if not channel:
            raise ValueError("log_channel must not be empty")
        return int(channel) if channel.isdigit() else channel
    raise ValueError("log_channel must be a channel number or interface name")


def select_log_channel(
    channels: Set[LogChannel], requested: Optional[LogChannel]
) -> LogChannel:
    """Resolve the one bus a replay may decode against one target definition."""
    if not channels:
        raise CanLogError("the CAN log contains no readable channels")
    if requested is not None:
        if requested not in channels:
            available = ", ".join(
                str(channel) for channel in sorted(channels, key=channel_sort_key)
            )
            raise CanLogError(
                f"channel {requested!r} is not present in the CAN log; "
                f"available channels: {available}"
            )
        return requested
    if len(channels) == 1:
        return next(iter(channels))
    available = ", ".join(
        str(channel) for channel in sorted(channels, key=channel_sort_key)
    )
    raise CanLogError(
        f"the CAN log contains multiple channels ({available}); choose log_channel"
    )


def _parse_identifier(token: str, base: int) -> Optional[Tuple[int, bool]]:
    match = _ID_RE.match(token)
    if match is None:
        return None
    digits, extended_flag = match.group(1), match.group(2) == "x"
    try:
        frame_id = int(digits, base)
    except ValueError:
        return None
    ceiling = MAX_EXTENDED_FRAME_ID if extended_flag else MAX_STANDARD_FRAME_ID
    if frame_id > ceiling:
        # An identifier too wide for the width it claims is a mis-read column,
        # not a frame. Counting it would put an address on screen that no ECU
        # can hold.
        return None
    return frame_id, extended_flag


def _parse_payload(tokens: Sequence[str], length: int) -> Optional[bytes]:
    if len(tokens) < length:
        return None
    try:
        return bytes(int(token, 16) for token in tokens[:length])
    except ValueError:
        return None


#: Longest decimal field this reader will convert. ``int()`` refuses a string
#: of more than 4300 digits and raises ValueError, and this reader's contract
#: is that a line it cannot parse is counted and skipped, never fatal. No
#: column in an ASC log -- a DLC, a channel, a length -- is more than a few
#: digits, so a longer one means the line is not what it claims to be.
MAX_DECIMAL_DIGITS = 18


def _is_decimal(token: str) -> bool:
    return token.isdigit() and len(token) <= MAX_DECIMAL_DIGITS


def _consume_frame_body(
    tokens: Sequence[str], *, fd: bool
) -> Optional[Tuple[bool, bytes]]:
    """Read ``[name] [brs esi] [d|r] <dlc> [length] <data...>`` into a payload.

    The optional columns are what make one routine serve both the classic and
    the CAN FD line shapes, and both CAN FD column orders. Everything optional
    here is optional in some real writer's output; nothing is optional to make
    a malformed line pass.

    Returns the remote flag and the payload, or ``None`` when the columns do
    not form a frame -- which is the signal to count the line as unparsable
    rather than to publish a guess.
    """
    index = 0
    # A symbolic message name, when the writer emitted one. Never a bare
    # integer, so it cannot be confused with the numeric columns that follow.
    if index < len(tokens) and not _is_decimal(tokens[index]) and tokens[index] not in {"d", "r"}:
        index += 1

    if fd:
        # BRS and ESI. Present in every CAN FD line; their absence means the
        # columns are not the ones this expects.
        if index + 1 >= len(tokens) or not (
            _is_decimal(tokens[index]) and _is_decimal(tokens[index + 1])
        ):
            return None
        index += 2

    is_remote = False
    if index < len(tokens) and tokens[index] in {"d", "r"}:
        is_remote = tokens[index] == "r"
        index += 1

    if index >= len(tokens) or not _is_decimal(tokens[index]):
        return None
    dlc = int(tokens[index])
    index += 1

    length = DLC_TO_LENGTH.get(dlc)
    if length is None:
        return None

    # CAN FD states the byte count in its own column. When it is there the two
    # must agree: a DLC and a length that disagree mean the columns have been
    # read at the wrong offset, and the payload that follows is not the one
    # this line describes.
    if fd:
        if index >= len(tokens) or not _is_decimal(tokens[index]):
            return None
        stated = int(tokens[index])
        if stated != length:
            return None
        index += 1

    if is_remote:
        # A remote frame requests a payload rather than carrying one.
        return True, b""

    payload = _parse_payload(tokens[index:], length)
    if payload is None:
        return None
    return False, payload


class AscLogReader:
    """A Vector ASC log, read as a stream of frames.

    Streaming rather than loading: an ASC of a busy bus runs to hundreds of
    megabytes, and a replay that has to fit the whole log in memory before
    showing the first row is a replay that fails on the logs worth replaying.

    Read :attr:`stats` after iterating to find out what the read actually saw.
    """

    format = "asc"

    def __init__(
        self,
        path: str | Path,
        *,
        channel: Optional[LogChannel] = None,
        max_frames: Optional[int] = None,
    ) -> None:
        self.path = Path(path)
        #: Which bus in the log to replay. A multi-channel ASC holds several
        #: buses, and decoding all of them against one target bus is how a
        #: replay produces values that look right and are not -- so a caller
        #: that knows which channel it wants says so.
        self.channel = channel
        self.max_frames = max_frames
        self.stats = LogReadStats(format=self.format)
        self._base = 16
        self._epoch = 0.0

    def messages(self) -> Iterator[ReplayMessage]:
        """Yield frames until the log or the frame budget runs out."""
        try:
            handle = self.path.open("r", encoding="utf-8", errors="replace")
        except OSError as error:
            raise CanLogError(f"cannot read CAN log {str(self.path)!r}: {error}") from error

        with handle:
            for line in handle:
                tokens = line.split()
                if not tokens:
                    continue
                if self._read_directive(tokens):
                    continue

                message = self._read_frame(tokens)
                if message is None:
                    continue

                observed_channel = message.channel if message.channel is not None else 0
                self.stats.channels_present.add(observed_channel)
                if self.channel is not None and observed_channel != self.channel:
                    continue

                if message.is_error_frame:
                    self.stats.error_frames += 1
                else:
                    self.stats.frames += 1
                if self.stats.first_timestamp is None:
                    self.stats.first_timestamp = message.timestamp
                self.stats.last_timestamp = message.timestamp

                yield message

                if self.max_frames is not None and self.stats.frames >= self.max_frames:
                    self.stats.truncated = True
                    return

    # ── header ────────────────────────────────────────────────────────

    def _read_directive(self, tokens: List[str]) -> bool:
        """Consume a header line, returning whether it was one.

        A directive is recognised by its keyword rather than by its position:
        ASC writers put ``base`` and ``timestamps`` on one line or two, and in
        either order.
        """
        head = tokens[0]
        if head.startswith("//"):
            return True
        if head == "date":
            self._read_date(tokens[1:])
            return True
        if head in {"base", "internal"} or (head in {"Begin", "End"} and len(tokens) > 1):
            if "hex" in tokens:
                self._base = 16
            elif "dec" in tokens:
                self._base = 10
            return True
        if head in {"Measurement", "previous"}:
            return True
        # A frame line always opens with a timestamp. Anything else that does
        # not is a directive this reader has no use for.
        try:
            float(head)
        except ValueError:
            return True
        return False

    def _read_date(self, tokens: Sequence[str]) -> None:
        """Anchor the log's relative timestamps to the wall clock it recorded.

        Without this every ``first_seen_at`` in a replay renders as 1970, because
        an ASC counts seconds from the start of its own measurement. The log
        states when that was; using it is the difference between a timestamp an
        operator can correlate with anything else and one they cannot.
        """
        text = " ".join(tokens)
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            # An ASC date header is wall-clock time on the machine that
            # recorded it, with no zone stated. Reading it as local time is the
            # only available interpretation; stamping the zone on makes that
            # assumption visible in the result instead of leaving a bare naive
            # time that reads as UTC next to arrival times that are not.
            self.stats.started_at = parsed.astimezone()
            self._epoch = parsed.timestamp()
            return

    # ── frames ────────────────────────────────────────────────────────

    def _read_frame(self, tokens: List[str]) -> Optional[ReplayMessage]:
        try:
            timestamp = float(tokens[0]) + self._epoch
        except ValueError:
            return None

        if len(tokens) < 3:
            self.stats.unparsable_lines += 1
            return None

        # A bus fault is not traffic, and the aggregator tallies it separately.
        # Recognised before anything reads a column as an identifier, for the
        # same reason the live path classifies before it reads identity.
        if any(token.startswith("ErrorFrame") for token in tokens):
            return ReplayMessage(
                timestamp=timestamp,
                arbitration_id=0,
                data=b"",
                is_error_frame=True,
                channel=self._read_channel(tokens[1]),
            )

        if tokens[1] == "CANFD":
            return self._read_fd_frame(timestamp, tokens[2:])
        if tokens[1] == "CAN":
            # Some writers label classic lines explicitly.
            return self._read_classic_frame(timestamp, tokens[2:])
        return self._read_classic_frame(timestamp, tokens[1:])

    @staticmethod
    def _read_channel(token: str) -> Optional[int]:
        return int(token) if _is_decimal(token) else None

    def _read_fd_frame(self, timestamp: float, tokens: List[str]) -> Optional[ReplayMessage]:
        """Read a CAN FD line in either of the two column orders found in real logs.

        Vector's writer emits ``channel direction identifier``; tools that grew
        out of the classic-CAN line emit ``channel identifier direction``. The
        direction column is what tells them apart, so it is located rather than
        assumed.
        """
        if len(tokens) < 6:
            self.stats.unparsable_lines += 1
            return None
        channel = self._read_channel(tokens[0])

        if tokens[1] in _DIRECTIONS:
            identifier, rest = tokens[2], tokens[3:]
        elif len(tokens) > 2 and tokens[2] in _DIRECTIONS:
            identifier, rest = tokens[1], tokens[3:]
        elif _TX_REQUEST in tokens[1:3]:
            # Logged alongside the Tx it precedes; replaying both would count
            # every transmitted frame twice.
            return None
        else:
            self.stats.unparsable_lines += 1
            return None

        parsed_id = _parse_identifier(identifier, self._base)
        body = _consume_frame_body(rest, fd=True) if parsed_id else None
        if parsed_id is None or body is None:
            self.stats.unparsable_lines += 1
            return None

        frame_id, is_extended = parsed_id
        is_remote, payload = body
        return ReplayMessage(
            timestamp=timestamp,
            arbitration_id=frame_id,
            data=payload,
            is_extended_id=is_extended,
            is_remote_frame=is_remote,
            is_fd=True,
            channel=channel,
        )

    def _read_classic_frame(
        self, timestamp: float, tokens: List[str]
    ) -> Optional[ReplayMessage]:
        """Read ``<channel> <identifier> <direction> <d|r> <dlc> <data...>``."""
        if len(tokens) < 4:
            self.stats.unparsable_lines += 1
            return None
        channel = self._read_channel(tokens[0])

        if tokens[2] in _DIRECTIONS:
            identifier, rest = tokens[1], tokens[3:]
        elif tokens[1] in _DIRECTIONS:
            identifier, rest = tokens[2], tokens[3:]
        elif _TX_REQUEST in tokens[1:3]:
            return None
        else:
            self.stats.unparsable_lines += 1
            return None

        parsed_id = _parse_identifier(identifier, self._base)
        body = _consume_frame_body(rest, fd=False) if parsed_id else None
        if parsed_id is None or body is None:
            self.stats.unparsable_lines += 1
            return None

        frame_id, is_extended = parsed_id
        is_remote, payload = body
        return ReplayMessage(
            timestamp=timestamp,
            arbitration_id=frame_id,
            data=payload,
            is_extended_id=is_extended,
            is_remote_frame=is_remote,
            channel=channel,
        )


class PythonCanLogReader:
    """Stream a format handled by python-can into the replay message shape."""

    format = ""
    reader_name = ""
    one_based_channels = False

    def __init__(
        self,
        path: str | Path,
        *,
        channel: Optional[LogChannel] = None,
        max_frames: Optional[int] = None,
    ) -> None:
        self.path = Path(path)
        self.channel = channel
        self.max_frames = max_frames
        self.stats = LogReadStats(format=self.format)

    def messages(self) -> Iterator[ReplayMessage]:
        try:
            self._validate()
            from can import io

            reader_type: Type[Any] = getattr(io, self.reader_name)
            with reader_type(self.path) as source:
                for source_message in source:
                    message = self._convert(source_message)
                    observed_channel = message.channel if message.channel is not None else 0
                    self.stats.channels_present.add(observed_channel)
                    if self.channel is not None and observed_channel != self.channel:
                        continue

                    if message.is_error_frame:
                        self.stats.error_frames += 1
                    else:
                        self.stats.frames += 1
                    if self.stats.first_timestamp is None:
                        self.stats.first_timestamp = message.timestamp
                        self._set_started_at(message.timestamp)
                    self.stats.last_timestamp = message.timestamp

                    yield message

                    if self.max_frames is not None and self.stats.frames >= self.max_frames:
                        self.stats.truncated = True
                        return
        except CanLogError:
            raise
        # Reader implementations also surface format-specific exceptions from
        # struct/zlib. Keep those library details behind the public log error.
        except Exception as error:
            raise CanLogError(
                f"cannot parse {self.format.upper()} CAN log {str(self.path)!r}: {error}"
            ) from error

    def _validate(self) -> None:
        """Reject known unsupported variants before a reader can partially parse them."""

    def _convert(self, message: Any) -> ReplayMessage:
        channel = message.channel
        if self.one_based_channels and isinstance(channel, int):
            channel += 1
        return ReplayMessage(
            timestamp=float(message.timestamp),
            arbitration_id=int(message.arbitration_id),
            data=bytes(message.data),
            is_extended_id=bool(message.is_extended_id),
            is_error_frame=bool(message.is_error_frame),
            is_remote_frame=bool(message.is_remote_frame),
            is_fd=bool(message.is_fd),
            channel=channel,
        )

    def _set_started_at(self, timestamp: float) -> None:
        # Some BLF files contain only relative seconds and no wall-clock header.
        # Presenting those as January 1970 would claim precision the file does
        # not have; year 2000 is a conservative boundary for vehicle captures.
        if timestamp < 946_684_800:
            return
        try:
            self.stats.started_at = datetime.fromtimestamp(timestamp, timezone.utc)
        except (OverflowError, OSError, ValueError):
            self.stats.started_at = None


class BlfLogReader(PythonCanLogReader):
    format = "blf"
    reader_name = "BLFReader"
    # python-can exposes BLF's one-based channel field as zero-based.
    one_based_channels = True


class CandumpLogReader(PythonCanLogReader):
    format = "candump"
    reader_name = "CanutilsLogReader"


class TrcLogReader(PythonCanLogReader):
    format = "trc"
    reader_name = "TRCReader"

    def _validate(self) -> None:
        supported = {"1.0", "1.1", "1.3", "2.0", "2.1"}
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith(";$FILEVERSION="):
                    version = line.partition("=")[2].strip()
                    if version not in supported:
                        raise CanLogError(
                            f"unsupported PEAK TRC version {version!r}; "
                            "supported versions are 1.0, 1.1, 1.3, 2.0, and 2.1 "
                            "(TRC 3/CAN XL is not supported)"
                        )
                    return
                if not line.startswith(";"):
                    # Headerless TRC is the legacy 1.0 form.
                    return


#: Suffixes this can replay, mapped to the reader that reads them.
READERS = {
    ".asc": AscLogReader,
    ".blf": BlfLogReader,
    ".log": CandumpLogReader,
    ".trc": TrcLogReader,
}


def open_log(
    path: str | Path,
    *,
    channel: Optional[LogChannel] = None,
    max_frames: Optional[int] = None,
) -> AscLogReader | PythonCanLogReader:
    """Pick a reader for a log by its suffix.

    Refuses an unknown suffix by name rather than guessing from content. This
    also gives the UI and CLI one explicit list of accepted formats.
    """
    resolved = Path(path)
    reader = READERS.get(resolved.suffix.lower())
    if reader is None:
        supported = ", ".join(sorted(READERS))
        raise CanLogError(
            f"{resolved.name!r} is not a CAN log this can replay; "
            f"supported formats: {supported}"
        )
    if not resolved.is_file():
        raise CanLogError(
            f"no CAN log at {str(resolved)!r}. The path is read on the host running "
            "IoTSploit, which is not necessarily the host running the UI."
        )
    return reader(resolved, channel=channel, max_frames=max_frames)


def scan_log(
    path: str | Path,
    *,
    channel: Optional[LogChannel] = None,
    max_frames: Optional[int] = None,
) -> LogReadStats:
    """Read a log through once without keeping it, to learn what it covers.

    A progress bar needs to know the length of the thing it is measuring before
    the first frame is shown, and a log only states that by being read. So a
    replay reads the file twice: once to learn its duration, frame count and
    channels, and once to play it. The pass is cheap -- parsing is a few hundred
    milliseconds for a 3 MB log -- and the alternative is a progress bar that
    only learns its own scale at the moment it finishes, which is no progress
    bar at all.
    """
    reader = open_log(path, channel=channel, max_frames=max_frames)
    for _ in reader.messages():
        pass
    return reader.stats


def identities_from_log(
    path: str | Path,
    *,
    channel: Optional[LogChannel] = None,
    max_frames: Optional[int] = None,
) -> Set[Tuple[int, bool]]:
    """Distinct data-frame identities in a log, for scoring it against a target's buses.

    The live counterpart of this is
    :func:`~iotsploit_protocols.canbus.bus_match.observe_identities`, and it
    exists for the same reason: picking the wrong bus does not fail, it decodes
    every frame to a plausible wrong value. A log needs that check more than a
    live capture does, not less -- whoever recorded it is often not whoever is
    reading it back.
    """
    reader = open_log(path, channel=channel, max_frames=max_frames)
    return {
        (message.arbitration_id, message.is_extended_id)
        for message in reader.messages()
        if not message.is_error_frame and not message.is_remote_frame
    }
