#!/usr/bin/env python
"""Turn a DBC file into a target, or fold one into a target that exists.

Writes the JSON that `target_import` reads, rather than touching the database
directly, so the result can be looked at and diffed before anything is loaded.

    poetry run python tools/import_dbc.py vw_mqb.dbc vw_golf_mqb "VW Golf" \
        --bus-id bus_powertrain_can --bus-name "Powertrain CAN" \
        --out conf/vw_golf_mqb_target.json
    iotsploit> target_import conf/vw_golf_mqb_target.json

--onto folds a second bus into what was written before. Re-running with the
same file changes nothing, and re-running with an updated one replaces each
node's frames instead of appending, so there is no state to keep track of.
"""

from __future__ import annotations

import argparse
import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_django.tools.can_facet import FACET_KEY  # noqa: E402
from iotsploit_django.tools.dbc import apply_dbc  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dbc", help="path to the .dbc file")
    parser.add_argument("target_id")
    parser.add_argument("name")
    parser.add_argument("--bus-id", default="bus_can")
    parser.add_argument("--bus-name", default=None, help="defaults to the bus id")
    parser.add_argument("--source", default=None, help="where the DBC came from, recorded on the target")
    parser.add_argument("--onto", default=None, help="an existing target JSON to fold this DBC into")
    parser.add_argument("--out", required=True, help="target JSON to write")
    args = parser.parse_args()

    if args.onto:
        with open(args.onto) as handle:
            base = json.load(handle)["targets"][0]
    else:
        base = {
            "target_id": args.target_id,
            "name": args.name,
            "type": "vehicle",
            "status": "active",
            "properties": {},
        }
    if args.source:
        # Provenance rather than a copy: the DBC is not vendored, so this is
        # what lets the import be checked against its source later.
        base.setdefault("properties", {})["dbc_source"] = args.source

    with open(args.dbc) as handle:
        target = apply_dbc(base, handle.read(), bus_id=args.bus_id, bus_name=args.bus_name)

    with open(args.out, "w") as handle:
        json.dump({"targets": [target]}, handle, indent=2)
        handle.write("\n")

    facets = [c["facets"][FACET_KEY] for c in target["components"] if FACET_KEY in c.get("facets", {})]
    frames = sum(len(f["messages"]) for f in facets)
    signals = sum(len(m["signals"]) for f in facets for m in f["messages"])
    print(f"{args.out}: {len(target['components'])} components, {frames} frames, {signals} signals")
    print(f"load it with: target_import {args.out}")


if __name__ == "__main__":
    main()
