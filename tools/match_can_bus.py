#!/usr/bin/env python
"""Work out which documented CAN bus an interface is actually wired to.

A vehicle ARXML describes many buses -- this one describes eleven -- and an
adapter is plugged into exactly one of them. Picking the wrong one does not
fail: every frame id still resolves, every signal still decodes, and the values
are wrong. That is a worse outcome than an error, so this answers the question
from the traffic rather than from a guess.

It listens read-only for a few seconds, then scores each of the target's CAN
buses by how much of what it heard that bus documents. A bus wired to the
adapter explains nearly everything; a bus that is not explains some of it by
coincidence, because ids repeat across buses.

    poetry run python tools/match_can_bus.py zxd_v5_pi can0

Transmits nothing. Note that a CAN controller in normal mode acknowledges
frames in silicon, so attaching to a live bus is not electrically inert.
"""

from __future__ import annotations

import argparse
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402
from iotsploit_protocols.canbus import TargetCanCatalog  # noqa: E402
from iotsploit_protocols.canbus.errorframes import (  # noqa: E402
    is_error_frame,
    is_remote_frame,
)
from iotsploit_protocols.canbus.socketcan import (  # noqa: E402
    CaptureBudget,
    SocketCanConfig,
    SocketCanReceiver,
)


def observe(channel: str, seconds: float, fd: bool) -> set:
    """The distinct frame identities heard on ``channel``.

    Error frames are excluded before identity is read: after python-can masks
    off CAN_ERR_FLAG what remains is an error class, not an address, and
    counting one would add a phantom id to the evidence.
    """
    seen = set()
    config = SocketCanConfig(channel=channel, fd=fd)
    with SocketCanReceiver(config) as receiver:
        for message in receiver.frames(
            CaptureBudget(duration_s=seconds, max_frames=200_000)
        ):
            if is_error_frame(message) or is_remote_frame(message):
                continue
            seen.add((message.arbitration_id, bool(message.is_extended_id)))
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target_id")
    parser.add_argument("channel", help="SocketCAN interface, e.g. can0")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument(
        "--classic",
        action="store_true",
        help="open a classic socket; the default is FD, which reads both",
    )
    args = parser.parse_args()

    stored = TargetManager.get_instance().get_target(args.target_id)
    if stored is None:
        raise SystemExit(f"no target {args.target_id!r}")

    seen = observe(args.channel, args.seconds, not args.classic)
    if not seen:
        raise SystemExit(
            f"nothing was heard on {args.channel} in {args.seconds:g}s. The "
            "interface may be down, on the wrong bitrate, or the bus idle."
        )
    print(f"{len(seen)} distinct identities heard on {args.channel}\n")

    catalog = TargetCanCatalog.from_target(stored)
    rows = []
    for bus in catalog.buses:
        documented = {(f.frame_id, f.is_extended) for f in bus.frames}
        if documented:
            matched = seen & documented
            rows.append((len(matched), bus.bus_id, len(documented)))
    if not rows:
        raise SystemExit(f"target {args.target_id!r} documents no CAN frames")

    rows.sort(reverse=True)
    print(f"{'BUS':<26}{'MATCHED':<10}{'OF HEARD':<11}{'DOCUMENTED'}")
    for matched, bus_id, documented in rows:
        print(
            f"{bus_id:<26}{matched:<10}{matched / len(seen) * 100:>3.0f}%"
            f"{'':<7}{documented}"
        )

    best, best_bus, _ = rows[0]
    runner_up = rows[1][0] if len(rows) > 1 else 0
    print()
    if best == 0:
        print("No bus explains this traffic. Wrong ARXML, or wrong interface.")
    elif best == runner_up:
        print(
            f"Ambiguous: {best_bus} and another bus explain the traffic equally "
            "well. Listen for longer, or tell them apart another way."
        )
    else:
        unexplained = len(seen) - best
        print(f"Best match: {best_bus} ({best} of {len(seen)} heard)")
        if unexplained:
            print(
                f"{unexplained} identities are not documented on it. That is a "
                "finding about the ARXML, not necessarily a wrong match."
            )


if __name__ == "__main__":
    main()
