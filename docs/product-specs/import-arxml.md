# Importing an AUTOSAR ARXML target

IoTSploit can convert an AUTOSAR ARXML communication description into
reviewable target JSON. The converter uses `cantools` for CAN frames and
signals and reads the limited AUTOSAR topology that `cantools` does not expose:
ECU instances, communication clusters, connectors, Ethernet endpoints, and
socket metadata.

The conversion command does not write to the IoTSploit database. Importing the
generated JSON is a separate, explicit step.

## Prerequisites

Run commands from the repository root and use the Poetry environment:

```bash
poetry install
```

The ARXML file must be no larger than 256 MiB. Files containing DTD or entity
declarations are rejected.

## Convert an ARXML file

Choose a target ID that is not already used by another IoTSploit target:

```bash
poetry run python tools/import_arxml.py \
  "/path/to/vehicle.arxml" \
  new_unique_target_id \
  "Vehicle display name" \
  --out /tmp/new_vehicle_target.json
```

Arguments:

| Argument | Meaning |
|---|---|
| `arxml` | Path to the source ARXML file. |
| `target_id` | Stable, unique ID used by IoTSploit. |
| `name` | Human-readable name shown in the target list. |
| `--out` | Destination for the generated target JSON. |
| `--source` | Optional provenance label. The source filename is used by default. |

For example, to record an OEM release label:

```bash
poetry run python tools/import_arxml.py \
  "/data/oem/vehicle-v6.arxml" \
  vehicle_v6 \
  "Vehicle V6" \
  --source "OEM communication release V6.0" \
  --out /tmp/vehicle_v6_target.json
```

The command prints component, bus, frame, and signal counts followed by any
limitations detected in the source. Review both the warnings and the generated
JSON before importing it.

## Import the generated target

Start the IoTSploit console:

```bash
poetry run iotsploit
```

Then import the generated JSON:

```text
target_import /tmp/new_vehicle_target.json
```

When the database already contains targets, select:

```text
Skip existing (recommended)
```

This preserves every existing target. A generated target whose ID is already
present is skipped rather than overwritten. After the import, refresh the
Flutter target list and select the new target.

## Target mapping

The importer creates:

- one `ecu` component per AUTOSAR `ECU-INSTANCE`;
- one bus per CAN, LIN, or Ethernet communication cluster;
- `bus_member` edges from communication connector references;
- CAN frames and signals under their owning CAN bus;
- Ethernet network endpoints, IP addresses, sockets, ports, and VLAN metadata;
- a DoIP facet only when the source provides an ECU-owned endpoint with a
  logical address;
- provenance, source SHA-256, AUTOSAR schema, counts, and warnings under
  `properties.arxml_import`.

Stable IDs are derived from AUTOSAR short names, so converting the same source
again produces diffable JSON. Repeated CAN frame names or identifiers on
different buses remain separate bus-specific definitions.

## Partial system descriptions

An ARXML `SYSTEM` with category `ECU_SYSTEM_DESCRIPTION` is an ECU extract, not
proof of a complete vehicle description. IoTSploit therefore imports it as:

```json
{
  "type": "vehicle",
  "status": "draft"
}
```

Its import metadata also contains `complete_vehicle: false`. Add or reconcile
other ECU descriptions before treating that target as a complete vehicle
topology.

## Current limitations

- CAN frames and signals are converted; LIN and Ethernet communication
  payload definitions are currently topology metadata only.
- AUTOSAR CAN container frames retain `contained_messages`, but the current
  Flutter explorer does not expand the nested payloads.
- Signals wider than 64 bits are preserved without truncation, but downstream
  consumers must support wide raw values.
- A DoIP role or port does not establish an ECU logical address. The importer
  never invents one.
- There is no Flutter ARXML upload control. Conversion and database import are
  deliberately separate review steps.

## Troubleshooting

`cantools could not parse ...`
: The ARXML is malformed, unsupported, or fails strict CAN layout validation.
  The target is not generated.

`multiple communication clusters use short name ...`
: The source cannot map CAN messages to a unique bus by name. Correct or split
  the source rather than accepting an ambiguous target.

The new target does not appear in Flutter
: Confirm that `target_import` completed, then refresh the target list. Running
  only `import_arxml.py` creates JSON but does not change the database.

The target was skipped
: Its `target_id` already exists. Use a new ID, or explicitly choose the
  overwrite option only when replacing that target is intentional.
