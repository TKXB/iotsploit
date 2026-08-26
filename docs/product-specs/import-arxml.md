# Importing an AUTOSAR ARXML target

IoTSploit can convert an AUTOSAR ARXML communication description into a
reviewable vehicle target. The converter uses `cantools` for CAN frames and
signals and reads the limited AUTOSAR topology that `cantools` does not expose:
ECU instances, communication clusters, connectors, Ethernet endpoints, and
socket metadata.

There are two ways in, and both keep the same review boundary: parsing an ARXML
never changes a target, and creating one is a separate, explicit step.

| Route | Use it when |
|---|---|
| **Flutter — Targets → Import ARXML** | Normal operation. Upload, review, create. |
| **CLI — `tools/import_arxml.py` + `target_import`** | Scripting, an offline rig, or when you want the generated JSON on disk. |

Both routes create a **new** target. Importing into an existing target is not
supported: there is no merge and no overwrite.

## Import from Flutter

1. Open **Targets** and choose **Import ARXML**. On a phone-width window this
   is in the add menu beside **Add New Target**.
2. Choose the `.arxml` file. The extension is a convenience filter only —
   validity is decided by the rig's parser.
3. Enter a new target ID and display name, and optionally a source label to
   record provenance (an OEM release, say). The ID must not already exist; the
   dialog refuses one that does.
4. Press **Parse**. The file is uploaded and parsed on the rig. Nothing is
   written.
5. Review the preview: source, SHA-256, AUTOSAR schema, scope, the counts of
   components, buses, edges, CAN frames and signals, the buses with their frame
   counts, and every warning the parser produced.
6. Press **Create Target**. Only now does a target exist. Cancelling at any
   earlier point changes nothing.
7. The target list refreshes, and **Open in Explorer** opens the new target.
   Importing does not *select* a target — selecting stays a separate action.

### Limits and failure modes

| Situation | What happens |
|---|---|
| File over 256 MiB | Refused during the upload (HTTP 413). The rig stops reading rather than spooling the whole file first. |
| File over 32 MiB on the web build | Refused in the dialog. The web build has no file path to stream from, so it is bounded lower. Use the desktop app or the CLI. |
| Malformed or unsupported ARXML | Refused with the parser's reason (HTTP 400). No target is created. |
| DTD or entity declarations | Refused before any parsing. |
| Target ID already exists | Refused. Choose a different ID; there is no overwrite or merge option. |
| An `ECU_SYSTEM_DESCRIPTION` extract | Imports as a **draft** target. The dialog says so before you confirm, and the warning is stored in the target's import metadata. |

A large ARXML is CPU- and memory-intensive and occupies one synchronous rig
worker for the whole parse. Import one file at a time, and measure a
representative file before setting HTTP timeouts in front of the rig.

### Security boundary

The HTTP API is unauthenticated. `preview_arxml_import` accepts a file upload
and parses it, so the rig must stay on a trusted network or behind external
authentication. The endpoint is not exposed as an MCP tool.

The raw ARXML is never persisted: it lives in one temporary file for one parse
and is deleted on every exit path, including failures. Only the source label
(or the upload's basename — never a client path), its SHA-256, size, schema and
counts are stored on the target.

## Convert from the CLI

### Prerequisites

Run commands from the repository root and use the Poetry environment:

```bash
poetry install
```

The ARXML file must be no larger than 256 MiB. Files containing DTD or entity
declarations are rejected.

### Convert an ARXML file

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

### Import the generated target

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
- Import creates a new target only. Enriching an existing target from an ARXML
  is not implemented, and neither is re-importing a newer release over an
  earlier one.
- Parsing is synchronous. There is no background job and no durable progress
  for a long import.

## Troubleshooting

`cantools could not parse ...`
: The ARXML is malformed, unsupported, or fails strict CAN layout validation.
  The target is not generated.

`multiple communication clusters use short name ...`
: The source cannot map CAN messages to a unique bus by name. Correct or split
  the source rather than accepting an ambiguous target.

The new target does not appear in Flutter
: Confirm that `target_import` completed, then refresh the target list. Running
  only `import_arxml.py` creates JSON but does not change the database. From
  the import dialog, a target exists only after **Create Target**.

The target was skipped
: Its `target_id` already exists. Use a new ID, or explicitly choose the
  overwrite option only when replacing that target is intentional.
