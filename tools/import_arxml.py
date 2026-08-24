#!/usr/bin/env python
"""Convert an AUTOSAR ARXML file to reviewable IoTSploit target JSON.

The command does not write to Django.  Inspect the generated file, then load
it through the existing target import command:

    poetry run python tools/import_arxml.py vehicle.arxml vehicle_id "Vehicle" \
        --out conf/vehicle_target.json
    iotsploit> target_import conf/vehicle_target.json

An ``ECU_SYSTEM_DESCRIPTION`` is marked as a draft vehicle because it is an
ECU extract, not proof of a complete vehicle topology.
"""

from __future__ import annotations

import argparse

from iotsploit_protocols.autosar.arxml import (
    ArxmlImportError,
    dump_target,
    import_arxml,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("arxml", help="path to the .arxml file")
    parser.add_argument("target_id")
    parser.add_argument("name")
    parser.add_argument(
        "--source",
        default=None,
        help="source/provenance recorded in metadata; defaults to the filename",
    )
    parser.add_argument("--out", required=True, help="target JSON to write")
    args = parser.parse_args()

    try:
        result = import_arxml(
            args.arxml,
            target_id=args.target_id,
            name=args.name,
            source=args.source,
        )
        dump_target(result, args.out)
    except ArxmlImportError as exc:
        parser.error(str(exc))

    counts = result.counts
    print(
        f"{args.out}: {counts['components']} components, {counts['buses']} buses, "
        f"{counts['can_messages']} CAN frames, {counts['can_signals']} signals"
    )
    for warning in result.warnings:
        print(f"warning: {warning}")
    print(f"review it, then load it with: target_import {args.out}")


if __name__ == "__main__":
    main()
