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


can_parser = cmd2.Cmd2ArgumentParser(description="Capture or monitor decoded CAN traffic live")
can_sub = can_parser.add_subparsers(dest="action", required=True)


def _common(parser):
    parser.add_argument("--target", required=True, help="target id containing the CAN definitions")
    parser.add_argument("--bus", required=True, help="CAN bus id on the target")
    parser.add_argument("--channel", required=True, help="SocketCAN interface, for example can0")
    parser.add_argument("--max-frames", type=_positive, help="hard frame ceiling")
    parser.add_argument("--snapshot-ms", type=_positive, default=200, help="table update interval")
    parser.add_argument("--classic", action="store_true", help="open a classic-CAN socket instead of CAN FD")
    parser.add_argument("--no-decode", action="store_true", help="show identities and payloads without decoding")


capture_parser = can_sub.add_parser("capture", help="bounded live capture that records observations")
_common(capture_parser)
capture_parser.add_argument("--seconds", type=_positive, default=30, help="capture duration")

monitor_parser = can_sub.add_parser("monitor", help="live monitor until Ctrl-C or its safety ceiling")
_common(monitor_parser)
monitor_parser.add_argument("--ceiling-seconds", type=_positive, default=3600, help="forgotten-session ceiling")


class CanCommands(BaseCommands):
    """Target-aware decoded CAN capture and monitor commands."""

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(can_parser)
    def do_can(self, args):
        """Capture or monitor decoded CAN traffic live."""
        mode = args.action
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
