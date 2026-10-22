#!/usr/bin/env python
"""Record simulated CAN observations against a target, for testing.

There is no CAN sniffer plugin yet, so a target imported from a DBC has a
complete picture of what its ECUs *should* send and nothing at all about what
was actually seen. This fills in the second half so the observation views have
something to render.

The facts are derived from the target's own ``can`` facets, so every frame id
is one that really exists on that target, and only a fraction of the declared
frames are recorded as seen -- which is the interesting case: the gap between
what the DBC claims and what a capture found.

**This is not a measurement.** Everything it writes carries the source
``can_sniff_sim`` so it can be told apart from a real scan at a glance, and
removed with --clear. Do not read it as evidence about a vehicle.

    poetry run python tools/seed_can_observations.py vw_golf_mqb
    poetry run python tools/seed_can_observations.py vw_golf_mqb --fraction 0.5
    poetry run python tools/seed_can_observations.py vw_golf_mqb --clear
"""

from __future__ import annotations

import argparse
import os
import random
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_core.domain.observation import Fact  # noqa: E402
from iotsploit_django.adapters.django.observation_models import ScanRunDBModel  # noqa: E402
from iotsploit_django.adapters.django.observation_repository import ObservationRepository  # noqa: E402
from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402
from iotsploit_django.tools.can_facet import FACET_KEY, CanFacet, canonical_frame_id  # noqa: E402

#: Never a real tool name. Anything under this source is simulated.
SOURCE = "can_sniff_sim"

#: Plausible cycle times, picked per frame so the values are not all identical.
PERIODS_MS = (10, 20, 50, 100, 200, 500, 1000)


def build_facts(facet: CanFacet, rng: random.Random, fraction: float) -> list[Fact]:
    """One fact per frame the simulated capture 'saw'.

    A frame that was not seen produces no fact rather than a false one: absence
    from a complete snapshot is already how this model says "not there".
    """
    facts = []
    for message in facet.messages:
        if rng.random() > fraction:
            continue
        period = rng.choice(PERIODS_MS)
        facts.append(
            Fact(
                protocol="can",
                subject_kind="message",
                subject_id=canonical_frame_id(message.frame_id, message.is_extended),
                observed_property="seen",
                value={
                    "name": message.name,
                    "count": max(1, round(60_000 / period)),
                    "period_ms": period,
                    "dlc": message.dlc,
                },
            )
        )
    return facts


def clear(target_id: str) -> int:
    """Drop every simulated scan for a target. Observations cascade."""
    session = ObservationRepository()._session_factory()
    try:
        removed = (
            session.query(ScanRunDBModel)
            .filter(ScanRunDBModel.target_id == target_id, ScanRunDBModel.source == SOURCE)
            .delete(synchronize_session=False)
        )
        session.commit()
        return removed
    finally:
        session.close()


def seed(target_id: str, fraction: float, seed_value: int) -> int:
    manager = TargetManager.get_instance()
    row = next((t for t in manager.get_all_targets() if t["target_id"] == target_id), None)
    if row is None:
        sys.exit(f"no target {target_id!r}")

    target = manager.create_target_instance(row)
    rng = random.Random(seed_value)
    total = 0

    for component in target.components:
        facet = component.facet(FACET_KEY)
        if not isinstance(facet, CanFacet) or not facet.messages:
            continue

        facts = build_facts(facet, rng, fraction)
        # The bus is named in the scope key rather than in a field of its own:
        # ObservationScope has component_id and nothing for a bus, so this is
        # the closest a bus-wide capture can currently get to saying where it
        # listened. Two captures on different buses stay incomparable, which is
        # the property that matters.
        repository = ObservationRepository()
        scan_id = repository.start_scan(
            target_id=target_id,
            source=SOURCE,
            scope_key=f"can:{facet.bus_id}",
            component_id=component.component_id,
        )
        repository.complete_scan(scan_id, facts, is_complete=True)
        total += len(facts)
        print(f"  {component.name:<26} {len(facts):3d} of {len(facet.messages):3d} frames seen")

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_id")
    parser.add_argument("--fraction", type=float, default=0.7, help="share of declared frames seen (default 0.7)")
    parser.add_argument("--seed", type=int, default=1, help="rng seed, so runs are reproducible")
    parser.add_argument("--clear", action="store_true", help="remove simulated scans instead of adding any")
    args = parser.parse_args()

    if args.clear:
        print(f"removed {clear(args.target_id)} simulated scans from {args.target_id}")
        return

    total = seed(args.target_id, args.fraction, args.seed)
    print(f"recorded {total} facts on {args.target_id} as source {SOURCE!r}")


if __name__ == "__main__":
    main()
