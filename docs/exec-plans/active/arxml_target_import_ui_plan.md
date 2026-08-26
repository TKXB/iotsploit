# ARXML Import UI — Create-New Target Plan

## Status

Active. Option B is approved; Release 1 implementation is under way on
`feat/arxml-import-api` (Django) and `feat/arxml-import-ui` (Flutter, stacked
on the API branch).

**Approved Release 1 decision:** add a Flutter workflow that uploads an ARXML,
parses it on the Django rig, previews the complete generated vehicle target,
and creates a **new** target only after explicit confirmation.

Importing into an existing target is not part of Release 1. The earlier safe
add-only merge design is retained below as a deferred Release 2 appendix so it
can be evaluated against actual import usage rather than implemented on
assumption.

This plan does not authorize implementation by itself. Move it to `active/`
when work starts and record deviations here rather than silently changing the
contracts or merge rules.

## Objective

Let a Flutter operator select an AUTOSAR ARXML file, parse its topology, CAN
frames, and signals on the Django rig, review the result, and explicitly create
a new target from the generated target document.

The import must preserve the current review boundary: parsing an ARXML file is
read-only, and no target changes until the operator has seen the counts,
warnings and confirms the final preview.

## Release Boundary

Release 1 implements only:

```text
ARXML upload -> read-only preview -> explicit create_target -> Target Explorer
```

Release 1 does not offer an existing target as a destination and does not
implement merge planning, bus mapping, conflict resolution, target digests, or
changes to `edit_target`.

After Release 1 has been used with representative ARXML files, record:

- how often operators need to enrich an existing target instead of creating a
  new one;
- which existing target data must survive;
- actual component, bus, and CAN-frame identity collisions;
- whether duplicate targets are an operational problem;
- parse time, peak memory, upload size, and generated target size.

Only then decide whether to activate the deferred add-only merge work.

## Non-goals

- Do not write a second ARXML parser. Reuse
  `iotsploit_protocols.autosar.arxml.import_arxml`.
- Do not silently overwrite existing components, buses, frames, signals,
  facets, properties, or edges.
- Do not import into or modify an existing target in Release 1.
- Do not remove target data because it disappeared from a later ARXML file.
- Do not implement managed ARXML re-import or source-owned deletion in this
  version.
- Do not add an `import_arxml` MCP mutation. MCP keeps the existing permitted
  target mutations (`create_target`, `edit_target`, `select_target`).
- Do not persist the raw OEM ARXML file.
- Do not add LIN or Ethernet payload decoding. The existing parser continues
  to import those protocols as topology/endpoint metadata only.
- Do not expand AUTOSAR container payloads in Flutter in this work.
- Do not redesign the target model or Target Explorer.

## Current State

The reusable importer already exists in
`iotsploit-protocols/src/iotsploit_protocols/autosar/arxml.py`.

It currently:

- accepts a filesystem path and returns `ArxmlImportResult` without changing
  backend state;
- uses `cantools` in strict ARXML mode for CAN messages and signals;
- extracts ECU instances, communication clusters, connectors, Ethernet
  endpoints, sockets, VLAN data, and limited DoIP configuration;
- derives stable component and bus IDs from AUTOSAR short names;
- stores CAN messages under `bus.properties.messages`;
- records source metadata, SHA-256, counts, schema, completeness, and warnings;
- marks an `ECU_SYSTEM_DESCRIPTION` target as draft;
- rejects files over 256 MiB and XML containing DTD/entity declarations.

The current operator flow is CLI-only:

```text
ARXML -> tools/import_arxml.py -> reviewable target JSON -> target_import
```

The Django `create_target` and `edit_target` endpoints already accept complete
`components`, `buses`, and `edges`. `edit_target` replaces each supplied list
wholesale; it is not an object-level merge endpoint.

Flutter already displays the generated shape. Target Explorer reads bus-owned
frames, expands a frame into signals, and renders signal layout, scaling,
range, unit, and multiplexing fields. The missing parts are file upload,
preview, and create confirmation.

The ordinary Flutter “Add New Target” flow must not be reused as-is because its
payload currently omits buses and edges.

## Architecture Decision

Keep dependencies pointing inward:

```text
Flutter import dialog
        |
        v
Django HTTP/upload adapter
        |
        +--> iotsploit-protocols ARXML parser
        |
        +--> iotsploit-core Target validation
        |
        v
existing Django target persistence
```

- `iotsploit-core` remains unaware of ARXML, Django, multipart uploads, and
  `cantools`.
- `iotsploit-protocols` owns format-specific parsing. A future pure merge
  planner belongs there only if Release 2 is approved.
- Django adapts an uploaded file to the parser's path interface, validates the
  result, and uses the existing create write after confirmation.
- Flutter owns file selection, new-target identity, preview presentation, and
  explicit confirmation.

Do not add a generic parser port until there is a second host-side use case
that needs orchestration through such a port. The existing protocols package is
already shared by the CLI and Django.

## User Flows

### Create a new target

```text
Targets -> Import ARXML
        -> choose file
        -> choose “Create new target”
        -> enter unique target ID, display name, optional source label
        -> Parse
        -> review metadata, counts, buses, and warnings
        -> Create Target
        -> refresh target list
        -> open Target Explorer
```

The confirmation sends the parser-produced target unchanged to the existing
`POST /api/create_target/` endpoint, including components, buses, and edges.
The endpoint remains the final uniqueness and target-model validation boundary.

### Deferred: import into an existing target

This flow is **not implemented in Release 1**. It is retained as the candidate
Release 2 experience if operational evidence justifies merge support.

```text
Targets -> Import ARXML
        -> choose file
        -> choose “Import into existing target”
        -> select an existing vehicle target
        -> Parse
        -> review candidate and map ARXML buses when needed
        -> preview additions, identical items, skipped items, and conflicts
        -> resolve every conflict without overwrite
        -> Confirm Merge
        -> edit target with optimistic precondition
        -> refresh and open Target Explorer
```

Only targets whose stored `type` is `vehicle` would be offered in a future
Release 2. Importing vehicle topology into a generic, router, camera, or ECU
target would require a separate product decision.

## HTTP Contracts

Endpoint names follow the repository's existing flat `/api/` target style.
Exact names may change during implementation only if all clients and tests are
updated together and the change is recorded in this plan.

Only the parse-preview contract and existing `create_target` confirmation are
Release 1 scope. Merge contracts are preserved as deferred design notes.

### 1. Parse and preview an upload

```http
POST /api/preview_arxml_import/
Content-Type: multipart/form-data
```

Fields:

| Field | Required | Meaning |
|---|---:|---|
| `file` | yes | ARXML upload |
| `target_id` | yes | unique ID for the proposed new target |
| `name` | yes | display name for the proposed new target |
| `source` | no | operator-provided provenance label; filename by default |

Successful response:

```json
{
  "status": "success",
  "candidate": {
    "target_id": "vehicle_v6",
    "name": "Vehicle V6",
    "type": "vehicle",
    "status": "active",
    "properties": {},
    "components": [],
    "buses": [],
    "edges": []
  },
  "counts": {
    "components": 19,
    "buses": 11,
    "edges": 27,
    "can_messages": 112,
    "can_signals": 1321,
    "can_fd_messages": 0,
    "can_container_messages": 0
  },
  "warnings": [],
  "complete_vehicle": true
}
```

This endpoint never writes a target and never retains the raw upload after the
response.

Error status:

| Status | Meaning |
|---:|---|
| 400 | missing metadata, invalid XML, unsupported ARXML, strict layout failure |
| 405 | wrong HTTP method |
| 413 | file exceeds the 256 MiB limit |
| 500 | unexpected server failure; do not expose local paths in the response |

### 2. Confirm a create

Use the existing endpoint:

```http
POST /api/create_target/
```

Send the complete `candidate`. A duplicate ID remains a 400 and requires the
operator to choose a different ID. Release 1 never offers overwrite or merge
as a duplicate-ID resolution.

### Deferred Release 2: Preview a merge

```http
POST /api/preview_arxml_merge/
Content-Type: application/json
```

Request:

```json
{
  "target_id": "existing_vehicle",
  "candidate": {},
  "bus_mappings": {
    "bus_can_powertrain": "bus_existing_powertrain"
  },
  "resolutions": {
    "frame:bus_existing_powertrain:123:standard": "skip_incoming"
  }
}
```

`candidate` is the complete target returned by the parse endpoint.
`bus_mappings` maps an imported bus ID to an existing compatible bus ID. An
unmapped imported bus keeps its stable imported ID and is proposed as new.
`resolutions` is optional on the first request and may only select supported
non-destructive actions.

Successful response:

```json
{
  "status": "success",
  "ready": false,
  "base_digest": "sha256-of-current-canonical-target",
  "merged_target": {},
  "summary": {
    "components": {"added": 4, "identical": 2, "skipped": 0, "conflicts": 1},
    "buses": {"added": 2, "mapped": 1, "identical": 0, "skipped": 0, "conflicts": 0},
    "frames": {"added": 112, "identical": 3, "skipped": 0, "conflicts": 2},
    "signals_added": 1321,
    "edges": {"added": 8, "identical": 3, "skipped": 0, "conflicts": 0}
  },
  "conflicts": []
}
```

`ready` is true only when every conflict has a valid resolution and the merged
target passes core target validation. Previewing a merge is read-only.

### Deferred Release 2: Confirm a merge

Use the existing endpoint:

```http
POST /api/edit_target/
```

Extend its request contract with an optional optimistic precondition:

```json
{
  "target_id": "existing_vehicle",
  "expected_digest": "digest-returned-by-merge-preview",
  "updates": {
    "properties": {},
    "components": [],
    "buses": [],
    "edges": []
  }
}
```

When `expected_digest` is present, Django canonicalizes and hashes the current
full target before applying updates. If it differs, return 409 and write
nothing. Flutter then reloads the target and repeats merge preview. Callers
that omit the field keep the existing edit behavior.

The write is all-or-nothing: do not persist a partial merge.

## Deferred Release 2: Canonical Digest

The optimistic precondition hashes the complete hydrated target serialized as
canonical JSON:

- UTF-8;
- sorted object keys;
- compact separators;
- stable list order as stored;
- SHA-256 hexadecimal digest.

Both preview and edit use one shared helper. Do not hash target summaries;
their facet and bus bulk is intentionally missing.

## Deferred Release 2: Add-only Merge Rules

Everything in this section is design reference, not Release 1 implementation
scope or acceptance criteria.

### Target identity and status

- Preserve the existing target's `target_id`, `name`, `type`, `status`,
  `ip_address`, and `location`.
- An ECU extract does not automatically downgrade an existing target to draft.
  Its `complete_vehicle: false` warning remains attached to that import.
- Never treat an imported candidate as authoritative for fields outside the
  imported topology layer.

### Import provenance

- Preserve existing target properties.
- Preserve an existing singular `properties.arxml_import` field for backward
  compatibility.
- Record merges in `properties.arxml_imports`, a list of import metadata
  entries keyed/deduplicated by source SHA-256.
- Each entry retains source label, SHA-256, size, AUTOSAR schema, system name,
  system category, completeness, counts, warnings, and import time.
- Repeating the same SHA-256 must not append duplicate provenance.
- Store the client filename basename or explicit source label, never a client
  absolute path.

### Components

Imported component identity is `component_id` plus `properties.arxml_ref`.

- If the ID is absent, add the component.
- If the ID and `arxml_ref` match and every overlapping imported field agrees,
  preserve the existing component and add only missing imported fields.
- Preserve existing fields and facets that the ARXML candidate does not name.
- If the ID exists without the same `arxml_ref`, report a component identity
  conflict.
- If the same field or facet key has a different value, report a conflict.
- The only v1 resolution for a component conflict is `skip_incoming`.
- No component-to-component mapping UI is included in v1.

### Buses

- An imported bus with an unused stable ID is proposed as a new bus.
- A bus mapping must point to an existing bus of the same type.
- Exact ID matches are preselected as mappings when types agree.
- Never infer a bus mapping from a similar display name alone.
- Preserve existing bus properties not named by the import.
- Conflicting scalar bus properties are reported; they are not overwritten.
- Skipping a bus also skips its imported frames and imported edges targeting
  that bus.

### CAN frames and signals

CAN frame identity is:

```text
(resolved bus_id, frame_id, is_extended)
```

The standard/extended flag is part of identity; standard `0x123` and extended
`0x123` are different frames.

- If no frame has that identity, add the whole frame with all signals.
- If the existing and incoming normalized frame definitions are identical,
  count it as identical and keep one copy.
- If any definition differs, report a frame conflict. Relevant differences
  include name, DLC, CAN FD flag, cycle time, header/container metadata,
  senders, or signal definitions.
- Signal comparison includes name, start bit, length, byte order, signedness,
  float flag, factor, offset, range, unit, choices, receivers, and multiplexing
  metadata.
- Do not merge two conflicting signal layouts field by field; a frame is the
  atomic definition unit.
- The only v1 resolution for a frame conflict is `skip_incoming`.

### Edges

Edge identity is `(resolved source, resolved target, relation)` after bus
mapping.

- Add an absent edge only when both endpoints resolve in the merged target.
- Keep one edge when identities and overlapping properties agree.
- Preserve existing extra edge properties.
- Conflicting values under the same property key are conflicts.
- Skipping a component or bus also skips dependent imported edges.

### Conflicts and resolutions

Each conflict has a deterministic ID, kind, imported identity, existing value,
incoming value, reason, and supported resolutions.

Supported v1 resolutions are deliberately limited:

- map an imported bus to a compatible existing bus;
- keep an imported bus as a new bus when its ID is unused;
- skip the incoming component;
- skip the incoming bus and its dependants;
- skip the incoming frame;
- cancel the import.

There is no overwrite resolution. A merge with unresolved conflicts is never
ready and cannot be confirmed through the import UI.

## Backend Implementation

### Deferred Release 2: Protocol merge package

Do not perform the work in this subsection during Release 1.

Add a pure merge module rather than growing the already large XML reader:

```text
iotsploit-protocols/src/iotsploit_protocols/autosar/merge.py
iotsploit-protocols/tests/test_arxml_merge.py
```

Suggested public API:

```python
plan_arxml_merge(
    existing_target,
    imported_target,
    *,
    bus_mappings=None,
    resolutions=None,
) -> ArxmlMergeResult
```

The function:

- performs no I/O;
- does not mutate either input;
- returns the proposed complete target, summary, conflicts, and readiness;
- produces deterministic ordering and conflict IDs;
- contains no Django imports;
- validates structural assumptions but leaves final `Target` validation to
  core/Django composition.

Export the public merge types/functions through
`iotsploit_protocols.autosar.__init__`.

### Django upload adapter and views

Prefer a dedicated handler rather than adding more format logic to
`target_views.py`:

```text
iotsploit-django/src/iotsploit_django/view_handlers/arxml_views.py
iotsploit-django/src/iotsploit_django/web/api/targets_urls.py
iotsploit-django/tests/test_arxml_import_endpoints.py
```

The upload adapter must:

- stream to a secure temporary file with an `.arxml` suffix;
- reject the upload while streaming once the parser's 256 MiB limit is
  exceeded, rather than waiting until disk has accepted the whole request;
- pass only that temporary path to the existing parser;
- delete the temporary file in `finally` on success, parser failure, client
  error, or unexpected exception;
- sanitize the displayed filename to its basename;
- return parser errors without server-local paths or tracebacks;
- avoid logging target payloads or OEM file contents.

Django normally spools large uploads to disk, but an endpoint-specific upload
limit is still required to bound temporary-disk use. Do not change a global
upload setting without checking the existing firmware/file-transfer features.

For Release 1, the parse-preview view validates the generated candidate through
the real Target hydration path and returns it without writing. Do not change
`edit_target`.

If Release 2 is later approved, its merge-preview view must load the full
target, never a `list_targets` summary, call the pure merge planner, validate a
ready proposal, and return the base digest. ARXML-specific merging must remain
outside the generic edit endpoint.

### MCP boundary

Do not register the preview endpoint or a new write operation as an MCP tool.
Existing agents can still create a fully formed target through the already
permitted mutation. This avoids expanding the unauthenticated MCP mutation
surface.

## Flutter Implementation

Add a dedicated import dialog and keep the normal target editor focused on
manual target editing:

```text
ui/lib/screens/targets/arxml_import_dialog.dart
ui/lib/services/targets_service.dart
ui/lib/screens/targets/targets_page.dart
ui/test/unit/targets_service_test.dart
ui/test/widget/arxml_import_dialog_test.dart
```

### Entry point

Add `Import ARXML` beside `Add New Target`. On narrow layouts, use one overflow
or add-action menu containing both choices rather than adding another tiny icon
with an ambiguous meaning.

### Dialog state machine

1. **File** — select one `.arxml` file and show filename/size.
2. **New target** — enter a unique target ID, display name, and optional source
   label.
3. **Parsing** — upload with cancel/progress where the HTTP stack supports it;
   prevent duplicate submissions.
4. **Import preview** — show source metadata, complete/draft scope, counts,
   buses, and every warning.
5. **Confirmation** — `Create Target`, with a clear statement that a new target
   will be added and no existing target will change.
6. **Completion** — refresh inventory and offer to open Target Explorer.

The dialog owns the complete candidate only for the duration of the workflow.
Do not persist it in Flutter preferences.

### Upload behavior

- Use the existing `file_picker` dependency.
- Stream the selected file where the platform API permits; do not request an
  entire 256 MiB file as in-memory bytes on desktop.
- If a platform cannot provide a bounded streaming upload, enforce a smaller
  documented platform-specific limit rather than risking process exhaustion.
- Filter for `.arxml` for usability, but rely on backend parsing—not the
  extension—for validity.
- Keep the file available until parsing completes. Confirmation uses the
  returned candidate JSON and does not upload/parse the ARXML again.

### Warning presentation

- `ECU_SYSTEM_DESCRIPTION` gets a persistent warning that the import is an ECU
  extract, not a complete vehicle.
- Container frames and wide signals show the parser's existing warnings
  verbatim as data, not as success toasts.
- A duplicate target ID disables confirmation and asks for a different new ID.
- Confirmation remains disabled until parsing and target validation succeed.

## Performance and Operational Boundaries

The parser intentionally reads the source twice: once for topology and once
through `cantools`, releasing the first object graph between passes. A large
ARXML import is CPU- and memory-intensive and occupies one synchronous Django
worker for the duration.

For this version:

- parse each uploaded file once per dialog workflow;
- return the candidate JSON to Flutter and reuse it for create confirmation;
- prevent repeated Parse clicks while a request is active;
- measure a representative production ARXML before setting request timeouts;
- document that the unauthenticated HTTP API must remain on a trusted network
  or behind external protection;
- do not claim support for concurrent large imports until measured.

Move to a staged/background-job design only if measurement shows that realistic
imports exceed HTTP timeouts, exhaust worker memory, or need durable progress.
That redesign is outside this plan.

## Validation and Error Handling

- Parse failures write nothing.
- Target validation failures write nothing and return a correctable 400.
- Duplicate target IDs write nothing and return a correctable 400.
- Database failures create no partial target and return 500.
- A successful create is immediately readable through `get_target` with
  the same components, buses, edges, frames, signals, and provenance that the
  operator confirmed.
- Selecting the target remains a separate operator action; import does not
  silently change the current target.

## Test Plan

Read `.agents/standards/testing.md` before adding or changing tests.

### Existing parser regression tests

Do not add merge tests or a merge module in Release 1. Extend the existing
ARXML parser tests only when the upload contract exposes an untested parser
boundary. Preserve coverage for:

- complete and partial system descriptions;
- CAN frames and lossless signal fields;
- stable bus/component IDs and valid edges;
- warnings, source metadata, and SHA-256;
- DTD/entity and oversize rejection.

### Deferred Release 2: Protocol merge unit tests

The following tests are retained for the later merge decision and are not
Release 1 gate items.

Cover:

- inputs are not mutated;
- a completely new component/bus/frame/edge is added;
- identical imports are deduplicated;
- repeated source SHA-256 does not duplicate provenance;
- an existing manual component with a colliding ID conflicts;
- matching `arxml_ref` allows non-conflicting additive fields and preserves
  existing extras;
- compatible explicit bus mapping rewrites frame/edge scope;
- cross-type bus mapping is rejected;
- standard and extended frames with the same numeric ID remain distinct;
- identical frames are skipped;
- any frame/signal definition difference conflicts;
- skip resolutions remove the correct incoming item and dependent edges;
- unresolved conflicts keep `ready` false;
- deterministic conflict IDs and output ordering;
- a ready merge hydrates as a valid core `Vehicle`.

### Django contract tests

Cover:

- multipart happy path returns candidate/counts/warnings and writes no target;
- missing file/metadata, malformed XML, strict cantools failure, DTD/entity,
  and oversize upload;
- temporary file deletion on every exit path;
- filename/path sanitization;
- create round-trip retains imported buses, frames, and signals;
- duplicate target ID writes nothing;
- parser preview never creates or selects a target;
- no new MCP tool is registered.

Deferred Release 2 adds merge-preview, full-target loading, ready/conflicting
responses, digest match/staleness, and backward-compatible `edit_target` tests.

### Flutter tests

Cover:

- multipart request fields and response parsing;
- canceling file selection is not an error;
- new-target identity fields are validated;
- parser warnings and draft scope remain visible;
- create confirmation includes buses and edges;
- duplicate ID keeps the dialog open and asks for a different ID;
- success refreshes the inventory and exposes the Explorer action;
- narrow-layout entry point remains usable.

Deferred Release 2 adds existing-target selection, bus mapping, conflict,
resolution, digest, and stale-write UI tests.

### Regression and full gates

Before each Python-code commit:

```bash
tools/testing/test-python-full.sh
```

Before each Flutter-code commit:

```bash
tools/testing/test-flutter-full.sh
```

Also verify manually with a representative ARXML on the rig:

1. preview without a database write;
2. create a new target;
3. open a bus-owned frame and its signals in Target Explorer;
4. attempt a duplicate ID and confirm no target changes;
5. import an ECU extract and confirm draft status and warnings;
6. cancel before confirmation and confirm no target changes.

## Implementation Phases

Each phase should be independently reviewable. Do not begin the next phase
while the current phase's focused tests fail.

### Phase 0 — Measure and freeze the create contract

- [x] Read `.agents/standards/testing.md`.
- [x] Select or synthesize license-safe fixtures for a complete system, ECU
      extract, DTD/entity rejection, malformed input, and oversize input.
      All five are hand-written in `test_arxml_import_endpoints.py`; the
      complete-system and ECU-extract fixtures are real ARXML that `cantools`
      parses in strict mode, so no parser is mocked.
- [ ] Record representative production-file parse time, peak memory, source
      size, candidate JSON size, and component/bus/frame/signal counts.
      **Outstanding — no OEM file is available in this working copy.** The
      synthetic fixture measures: 3 932 B source, 18 ms parse, 1.0 MiB peak
      (tracemalloc), 1 581 B candidate JSON, 1 component / 1 bus / 1 frame /
      1 signal. That bounds nothing about a production file; measure before
      setting request timeouts.
- [x] Freeze the multipart preview response and create confirmation contracts
      in tests.
- [x] Confirm a generated candidate round-trips through `create_target`
      without losing buses, edges, frames, or signals.

**Exit:** Release 1 feasibility is measured and its two HTTP contracts are
executable in tests; no production behavior changes.

### Phase 1 — Upload and parse preview

- [x] Add endpoint-specific bounded upload handling.
- [x] Add the parse preview view and URL.
- [x] Adapt the temporary path to the existing importer.
- [x] Validate the candidate through the real target hydration path.
- [x] Normalize parser failures and guarantee temporary-file cleanup.
- [x] Add contract tests for success, all rejection paths, and no database
      writes.

**Exit:** an HTTP client can upload once and receive the complete reviewable
candidate safely.

### Phase 2 — Flutter service and create-new import dialog

- [ ] Add a service method for multipart ARXML parse preview and a complete
      target create method if one is not already shared.
- [ ] Add streaming/platform-bounded upload behavior.
- [ ] Implement the dialog state machine and responsive Targets entry point.
- [ ] Implement new target ID/name/source validation, warnings, counts, bus
      summary, and explicit create confirmation.
- [ ] Send the complete candidate on create, including buses and edges.
- [ ] Handle duplicate IDs without overwrite or merge options.
- [ ] Refresh inventory and link to Target Explorer after success.
- [ ] Add service and widget tests.

**Exit:** a user can create and inspect a new ARXML-derived target without the
CLI and without hiding parser warnings.

### Phase 3 — Documentation, rig validation, and completion

- [ ] Update `docs/product-specs/import-arxml.md` with the create-new UI
      workflow, API limits, duplicate-ID behavior, and retained CLI fallback.
- [ ] Document trusted-network/authentication limitations.
- [ ] Run both full test gates.
- [ ] Perform the manual rig validation sequence.
- [ ] Record final measurements, test counts, deviations, and commit IDs here.
- [ ] Move this plan to `docs/exec-plans/completed/` only after all acceptance
      criteria pass.

## Expected File Impact

| File | Change |
|---|---|
| `iotsploit-django/src/iotsploit_django/view_handlers/arxml_views.py` | upload and preview views |
| `iotsploit-django/src/iotsploit_django/web/api/targets_urls.py` | parse-preview route |
| `iotsploit-django/tests/test_arxml_import_endpoints.py` | upload/preview/create contracts |
| `ui/lib/services/targets_service.dart` | ARXML preview and complete create calls |
| `ui/lib/screens/targets/arxml_import_dialog.dart` | dedicated workflow UI |
| `ui/lib/screens/targets/targets_page.dart` | import entry point and refresh |
| `ui/test/unit/targets_service_test.dart` | service request/response tests |
| `ui/test/widget/arxml_import_dialog_test.dart` | dialog state/create tests |
| `docs/product-specs/import-arxml.md` | operator and limitation updates |

Avoid touching the existing parser unless a test proves a parser defect. Avoid
changing Target Explorer unless imported data exposes a separate rendering bug.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Large files exhaust memory/disk or block workers | bounded streaming upload, one parse per workflow, measurements, documented synchronous limit |
| Duplicate target ID surprises the operator | pre-check for usability; `create_target` remains final authority and refuses duplicates |
| UI drops imported topology | send the complete parser candidate; contract-test buses, edges, frames, and signals |
| Client alters preview data before create | `create_target` hydrates and validates the complete candidate before persistence |
| New unauthenticated processing surface | trusted-network documentation, bounded upload, no new MCP tool |
| OEM ARXML leaks through logs or storage | temporary deletion, basename-only provenance, no payload/content logging |
| Partial ECU extract is mistaken for a vehicle | persistent draft/completeness warning before confirmation and in stored metadata |

## Acceptance Criteria

The plan is complete when all of the following are true:

1. Selecting and parsing an ARXML file changes no target.
2. The preview shows source metadata, scope/completeness, counts, and every
   warning returned by the existing parser.
3. Creating a new target retains components, buses, edges, CAN frames, and all
   signal fields and is viewable in Target Explorer.
4. Release 1 offers only new-target creation and never calls `edit_target`.
5. A duplicate target ID is rejected without changing the existing target and
   without offering overwrite.
6. Canceling before confirmation changes no target.
7. An ECU extract remains draft and its incomplete-vehicle warning is visible
   before and after creation.
8. The raw ARXML is deleted after parsing and is never stored in the target or
    logs.
9. No new MCP mutation is exposed.
10. Existing CLI conversion/import remains functional as a fallback.
11. Focused tests and both repository full test gates pass.

## Deferred Follow-up

The first deferred decision is whether to implement the add-only merge design
documented above. Do not begin it automatically after Release 1. Promote it to
a separate active plan only when usage evidence shows that creating a separate
target is insufficient and the real collision cases have been recorded.

If add-only merge is approved, its work includes the pure merge planner,
existing-target selection, bus mapping, conflict/skip UI, canonical target
digest, optimistic `edit_target` precondition, and its deferred tests and
acceptance criteria.

Managed re-import (“replace only facts previously owned by this same ARXML
source”) remains a later and separate problem. It requires source ownership
below the target level, a preview of additions/changes/removals, and an explicit
removal policy. Add-only merge must not claim to solve it.

Other deferred work:

- component-to-component mapping;
- overwrite conflict resolution;
- target-type conversion;
- background parsing jobs and durable progress;
- persistent raw ARXML artifact retention;
- multi-file import as one transaction;
- LIN/Ethernet payload decoding;
- AUTOSAR container expansion in Flutter;
- DBC/FIBEX reuse of the same UI after their merge semantics are separately
  specified.

## Completion Record

- Start date: 2026-08-26
- Completion date:
- Commits:
- Python test gate: 1097 passed, 0 failed, 0 skipped, 42 warnings
  (`tools/testing/test-python-full.sh`, ruff clean).
- Flutter test gate:
- Representative ARXML measurements: synthetic fixture only — see Phase 0. A
  production OEM file has not been measured.
- Deviations from plan:
  1. The Flutter gate lives at `ui/tools/testing/test-flutter-full.sh` and runs
     from `ui/`, not at the repository root as the Test Plan wrote it.
  2. "No new MCP tool is registered" is already enforced by
     `iotsploit-mcp/tests/test_write_tools.py::test_the_write_surface_is_exactly_these_five`,
     which asserts the write surface is exactly five tools. No duplicate test
     was added to the Django suite.
  3. The bounded upload is a Django `TemporaryFileUploadHandler` subclass that
     raises `StopUpload` at the chunk crossing the limit. The size check around
     the temporary copy is kept as the fallback for the case where the body was
     already parsed upstream and the handler cannot be installed.
  4. The preview endpoint does not report whether `target_id` is already taken.
     Flutter pre-checks against the target list it already holds, and
     `create_target` stays the only authority. This keeps the response contract
     to what the plan specified.
- Deferred defects discovered:
