"""Canonical live CAN commands."""

from __future__ import annotations

import cmd2

from iotsploit_cli.can_live import CanLiveError, CanLiveRun, CanLiveSession

from .base_commands import BaseCommands


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("must be greater than zero")
    return parsed


can_parser = cmd2.Cmd2ArgumentParser(
    description="Capture or monitor decoded CAN traffic live, or replay a recorded log"
)
can_sub = can_parser.add_subparsers(dest="action", required=True)


def _target_and_bus(parser):
    parser.add_argument("--target", required=True, help="target id containing the CAN definitions")
    parser.add_argument("--bus", required=True, help="CAN bus id on the target")
    parser.add_argument("--max-frames", type=_positive, help="hard frame ceiling")
    parser.add_argument("--snapshot-ms", type=_positive, default=200, help="table update interval")
    parser.add_argument("--no-decode", action="store_true", help="show identities and payloads without decoding")


def _common(parser):
    _target_and_bus(parser)
    parser.add_argument("--channel", required=True, help="SocketCAN interface, for example can0")
    parser.add_argument("--classic", action="store_true", help="open a classic-CAN socket instead of CAN FD")


capture_parser = can_sub.add_parser("capture", help="bounded live capture that records observations")
_common(capture_parser)
capture_parser.add_argument("--seconds", type=_positive, default=30, help="capture duration")

monitor_parser = can_sub.add_parser("monitor", help="live monitor until Ctrl-C or its safety ceiling")
_common(monitor_parser)
monitor_parser.add_argument("--ceiling-seconds", type=_positive, default=3600, help="forgotten-session ceiling")

replay_parser = can_sub.add_parser(
    "replay", help="decode a recorded CAN log against the target, as if it were live"
)
_target_and_bus(replay_parser)
replay_parser.add_argument(
    "--file",
    required=True,
    dest="path",
    help="CAN log to replay (.asc), read on the host running the backend",
)
# Deliberately not spelled --channel. On the live commands that names a kernel
# interface; here it is a channel number inside the log, and one flag meaning
# two things is how a replay decodes the wrong bus without saying so.
replay_parser.add_argument(
    "--log-channel",
    type=int,
    help="which channel in the log to replay, when it holds more than one",
)


class CanCommands(BaseCommands):
    """Target-aware decoded CAN capture and monitor commands."""

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(can_parser)
    def do_can(self, args):
        """Capture or monitor decoded CAN traffic live, or replay a recorded log."""
        mode = args.action
        if mode == "replay":
            run = CanLiveRun(
                target_id=args.target,
                bus_id=args.bus,
                mode=mode,
                path=args.path,
                log_channel=args.log_channel,
                # A log ends by itself; the budget only bounds a log far larger
                # than anyone meant to open.
                max_frames=args.max_frames or 5_000_000,
                snapshot_interval_ms=args.snapshot_ms,
                decode=not args.no_decode,
            )
        else:
            duration_s = args.seconds if mode == "capture" else args.ceiling_seconds
            default_frames = 200_000 if mode == "capture" else 20_000_000
            run = CanLiveRun(
                target_id=args.target,
                bus_id=args.bus,
                channel=args.channel,
                mode=mode,
                duration_s=duration_s,
                max_frames=args.max_frames or default_frames,
                snapshot_interval_ms=args.snapshot_ms,
                decode=not args.no_decode,
                fd=not args.classic,
            )
        factory = getattr(self, "can_live_session_factory", None)
        session = factory() if factory is not None else CanLiveSession.from_environment()
        try:
            return session.run(run)
        except CanLiveError as error:
            self.perror(str(error))
            return None
