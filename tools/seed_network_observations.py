#!/usr/bin/env python
"""Record simulated observations against a target's non-CAN facets, for testing.

The sibling of ``seed_can_observations.py``, for every target whose bulk is not
CAN frames: a vehicle's ethernet interfaces and PF rules, a router's services,
a SOME/IP catalogue. Those targets declare in full what they *should* expose and
carry nothing about what a probe actually found, so the observation views have
nothing to render.

Nothing here knows what any of those protocols are. A fact is emitted for every
item of every *collection* a facet holds -- the same structural rule the
explorer uses to decide what is bulk -- so a facet nobody has taught the system
about still produces observations. Subject ids come from the item's own
identifying field, so every id is one that really exists on that target, and
only a fraction are recorded as seen: the gap between what is configured and
what a probe found is the interesting half.

**This is not a measurement.** Everything it writes carries the source
``net_probe_sim`` so it can be told apart from a real scan at a glance, and
removed with --clear. Do not read it as evidence about a device.

    poetry run python tools/seed_network_observations.py zxd
    poetry run python tools/seed_network_observations.py zxd --fraction 0.5
    poetry run python tools/seed_network_observations.py zxd --clear
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from typing import Any, Optional

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_core.domain.observation import Fact  # noqa: E402
from iotsploit_django.adapters.django.observation_models import ScanRunDBModel  # noqa: E402
from iotsploit_django.adapters.django.observation_repository import ObservationRepository  # noqa: E402
from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402

#: Never a real tool name. Anything under this source is simulated.
SOURCE = "net_probe_sim"

#: CAN has a seeder of its own that understands frame ids and cycle times.
SKIP_FACETS = {"can"}

#: What a probe is taken to have asked of each kind of subject. Falls back to
#: "seen", which is what the CAN seeder records and carries no other claim.
OBSERVED_PROPERTY = {
    "interface": "reachable",
    "rule": "forwards",
    "service": "responds",
    "port": "open",
}

#: Where a subject id comes from, most specific first. A collection whose items
#: match none of these is skipped rather than given a positional id: a fact
#: keyed by "item 3" cannot be reconciled with anything later.
ID_FIELDS = ("name", "id", "service_id", "bus_id", "address", "pi_visible_address")


def subject_id_of(item: dict[str, Any]) -> Optional[str]:
    """The item's own identifying value, as the string a later scan would use."""
    for field in ID_FIELDS:
        value = item.get(field)
        if isinstance(value, (str, int)) and f"{value}":
            return f"{value}"
    for field, value in item.items():
        if field.endswith("_id") and isinstance(value, (str, int)):
            return f"{value}"
    return None


def subject_kind_of(field: str) -> str:
    """The singular of a collection's name: ``interfaces`` describes interfaces."""
    return field[:-1] if field.endswith("s") and len(field) > 1 else field


def collections_of(facet: Any) -> dict[str, list]:
    """The list-valued fields of one facet, registered or not.

    Structure decides, not a declared type: an unregistered facet loads as a
    RawFacet whose extras carry the same lists, and those are exactly the
    targets this exists for.
    """
    values = facet.model_dump() if hasattr(facet, "model_dump") else dict(facet)
    return {key: value for key, value in values.items() if isinstance(value, list) and value}


def build_facts(key: str, field: str, items: list, rng: random.Random, fraction: float) -> list[Fact]:
    """One fact per item the simulated probe 'saw'.

    An item that was not seen produces no fact rather than a false one: absence
    from a complete snapshot is already how this model says "not there".
    """
    kind = subject_kind_of(field)
    facts: list[Fact] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        subject_id = subject_id_of(item)
        if subject_id is None:
            continue
        if rng.random() > fraction:
            continue
        facts.append(
            Fact(
                protocol=key,
                subject_kind=kind,
                subject_id=subject_id,
                observed_property=OBSERVED_PROPERTY.get(kind, "seen"),
                value={"rtt_ms": round(rng.uniform(0.2, 40.0), 1)},
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
        for key, facet in (component.facets or {}).items():
            if key in SKIP_FACETS:
                continue
            for field, items in collections_of(facet).items():
                facts = build_facts(key, field, items, rng, fraction)
                if not facts:
                    continue
                # One scope per collection, so a probe of the interfaces stays
                # comparable only with another probe of the interfaces. The
                # facet and field name it, because ObservationScope has nothing
                # else to say where a probe looked.
                repository = ObservationRepository()
                scan_id = repository.start_scan(
                    target_id=target_id,
                    source=SOURCE,
                    scope_key=f"{key}:{field}",
                    component_id=component.component_id,
                )
                repository.complete_scan(scan_id, facts, is_complete=True)
                total += len(facts)
                print(f"  {component.name:<14} {key}.{field:<12} {len(facts):3d} of {len(items):3d} seen")

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_id")
    parser.add_argument("--fraction", type=float, default=0.7, help="share of configured items seen (default 0.7)")
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
