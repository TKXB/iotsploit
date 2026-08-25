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
from iotsploit_protocols.canbus.bus_match import (  # noqa: E402
    observe_identities,
    score_buses,
)


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

    seen = observe_identities(args.channel, args.seconds, fd=not args.classic)
    if not seen:
        raise SystemExit(
            f"nothing was heard on {args.channel} in {args.seconds:g}s. The "
            "interface may be down, on the wrong bitrate, or the bus idle."
        )
    print(f"{len(seen)} distinct identities heard on {args.channel}\n")

    result = score_buses(TargetCanCatalog.from_target(stored), seen)
    if result.outcome == "no_buses":
        raise SystemExit(f"target {args.target_id!r} documents no CAN frames")

    print(f"{'BUS':<26}{'MATCHED':<10}{'OF HEARD':<11}{'DOCUMENTED'}")
    for row in result.rows:
        print(
            f"{row.bus_id:<26}{row.matched:<10}{row.coverage * 100:>3.0f}%"
            f"{'':<7}{row.documented}"
        )

    print()
    if result.outcome in {"none", "tie"}:
        print(result.as_dict()["message"])
    else:
        best = result.rows[0]
        unexplained = len(seen) - best.matched
        print(f"Best match: {best.bus_id} ({best.matched} of {len(seen)} heard)")
        if unexplained:
            print(
                f"{unexplained} identities are not documented on it. That is a "
                "finding about the ARXML, not necessarily a wrong match."
            )


if __name__ == "__main__":
    main()
