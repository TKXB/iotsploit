# CAN Recorded Log Format Expansion — Implementation Plan

Status: proposal. Research and external-log verification completed 2026-09-17.
No production or test code has been written.

This plan expands the CAN Bus Monitor's **Recorded log** source from Vector ASC
only to four replayable formats in total:

- existing Vector ASCII (`.asc`);
- Vector Binary Logging Format (`.blf`);
- Linux can-utils/candump log format (`.log`);
- PEAK PCAN trace format (`.trc`).

The work spans the root Python repository and the nested `ui/` Flutter
repository. They are separate Git repositories and must be implemented,
validated, reviewed, and committed independently.

## Objective

Let an operator upload an ASC, BLF, candump, or PCAN trace, select the one bus
inside that recording when it contains several, and replay it through the
existing target-aware CAN decoder and timeline without changing what a replay
means.

Equivalent traffic in any supported format must produce equivalent:

- frame identities, including standard versus extended identity;
- payloads and DLCs;
- CAN versus CAN FD classification;
- error-frame and remote-frame classification where the source format carries
  it;
- measured periods derived from the recording's timestamps;
- selected-channel isolation;
- decoded rows, totals, timeline snapshots, and recorded observations.

This is a reader-boundary extension, not a second replay engine. The existing
aggregator, codec, timeline, bus scorer, observation producer, and WebSocket
contract remain the owners of their current behavior.

## Interpretation and scope

“Recorded log” means **reading/replaying an existing file**. This plan does not
add recording or export from the live monitor.

### In scope

- Read `.blf`, canonical candump `.log`, and `.trc` in addition to `.asc`.
- Preserve classic CAN, extended IDs, CAN FD, remote frames, error frames,
  timestamps, and source channels when the format provides them.
- Inspect an uploaded log before replay so Flutter can show its format and
  channels.
- Require an explicit channel for a multi-channel recording.
- Allow numeric log channels and candump interface names such as `can0`.
- Apply the selected channel to replay and **Identify bus**.
- Keep the request schema at version 1 by widening the already-optional
  `transport.log_channel` value from numeric-only to numeric-or-string.
- Update CLI, HTTP, product documentation, and deterministic tests for that
  widened contract.
- Validate the finished feature against real public vehicle captures downloaded
  from immutable Internet sources.

### Explicit non-goals

- Writing ASC, BLF, candump, or TRC files.
- Replacing the existing custom ASC parser with `python-can.ASCReader`.
- Supporting arbitrary `.csv`; there is no single interoperable CAN CSV schema.
- MDF/MF4 in this milestone. It needs the currently absent `asammdf` dependency
  and should be a separately accepted packaging decision.
- CAN XL. The current normalized frame and decoder contracts are CAN/CAN FD.
- PEAK BTRC, Vector MDF, PCAP/PCAPNG, SQLite, proprietary logger databases, or
  compressed `*.gz` variants.
- Refactoring the generic upload service or changing its current in-memory
  buffering. Large-file streaming is existing debt shared by ASC and all other
  uploaded files; record it separately rather than coupling it to format
  dispatch.
- Changing live monitoring, raw SocketCAN mode, frame composition, target
  definitions, decoding, or observation semantics.
- Network access in the deterministic test gate.

## Why these three formats

There is no authoritative cross-industry market-share ranking for CAN log
formats. The selection maximizes distinct ecosystem coverage while reusing the
already locked `python-can` 4.6.1 dependency:

| Format | Ecosystem covered | First-release boundary |
| --- | --- | --- |
| BLF (`.blf`) | Vector CANoe/CANalyzer and tools exchanging Vector binary logs | CAN, CAN FD, remote/error frames, multiple channels; ignore non-CAN BLF objects |
| candump (`.log`) | Linux SocketCAN/can-utils and embedded/Linux capture workflows | Canonical `candump -l` / `candump -L` records; named interfaces; CAN/CAN FD; no generic text-log guessing |
| PCAN TRC (`.trc`) | PEAK PCAN-View, PCAN-Basic, PCAN-Explorer | Versions the locked reader supports, currently 1.0–2.1; reject TRC 3/CAN XL clearly |

Primary references:

- python-can file readers:
  <https://python-can.readthedocs.io/en/stable/file_io.html>
- Linux can-utils `candump` logging behavior:
  <https://github.com/linux-can/can-utils/blob/master/candump.c>
- PEAK CAN trace format specification:
  <https://www.peak-system.com/produktcd/Pdf/English/PEAK_CAN_TRC_File_Format.pdf>
- PEAK tooling and format versions:
  <https://www.peak-system.com/products/software/tools/peak-converter/>

If customer evidence shows that CANape/INCA/dSPACE exchange is more important
than PCAN, replace TRC with MF4 before implementation rather than adding a
fourth new format silently. That decision changes dependencies and deployment
size, so it is not an implementation detail.

## Current state verified in the tree

### Flutter

`ui/lib/screens/tasks/components/can_screen.dart` owns the Recorded log flow:

- `_buildLogField` says `Choose a .asc log`.
- `_pickLog` limits `FilePicker` to `allowedExtensions: ['asc']` and uploads
  the selected bytes to the backend.
- `_runReplay` sends `path` and `display_name`, but never `log_channel`.
- `_identifyBus` sends a log path but never `log_channel`.
- The source selector, target/bus selection, replay timeline, and transport bar
  are already format-agnostic.

No new reusable UI component is necessary. The existing `InputDecorator` plus
`DropdownButton` pattern shown throughout the screen and component showcase is
sufficient for a conditional Log channel field.

### Protocol layer

`iotsploit-protocols/src/iotsploit_protocols/canbus/logfile.py` already owns
all log parsing and selection:

- `ReplayMessage` is the normalized frame shape consumed downstream.
- `LogReadStats` carries frame/error counts, skipped lines, channels,
  timestamps, duration, and truncation.
- `AscLogReader` streams the file rather than loading it into memory.
- `READERS = {'.asc': AscLogReader}` is the single format-dispatch owner.
- `open_log`, `scan_log`, and `identities_from_log` are already reused by
  replay and bus identification.

The custom ASC parser is intentionally richer than python-can's ASC reader for
the real column-order variants already covered by tests. It stays unchanged
except where a common channel type or common reader contract requires a type
annotation to widen.

### Plugin, Django, and CLI

- `iotsploit-exploits/.../canbus/live_capture.py::_parse_file_request` coerces
  every `transport.log_channel` to `int`.
- The interactive replay path probes channels and also coerces the chosen
  value to `int`.
- `iotsploit-django/.../view_handlers/can_views.py::identify_can_bus` repeats
  the same numeric-only coercion.
- `iotsploit-cli/.../can_live.py::CanLiveRun.log_channel` is `int | None`, and
  the CLI argument is numeric-only.
- Replay already reads a log twice: once for authoritative duration/frame
  metadata and once to build the timeline. Neither pass depends on ASC syntax;
  both call the protocol-layer reader boundary.

### Correctness defect exposed by new formats

The product guide says a multi-channel log must replay one channel, but the
Flutter scripted request omits `log_channel`. Today that means all ASC channels
can be folded into one target bus. BLF recordings commonly contain several
channels, and candump uses string interface names, so adding suffixes without
repairing this path would multiply an existing silent-wrong-decode risk.

The implementation must therefore ship format support and explicit channel
selection together. A multi-channel file with no selected channel is refused;
it is never combined or defaulted to the first channel.

## External real-log research record

The following files were downloaded to
`/tmp/can-log-format-research/` on 2026-09-17. They are research artifacts, not
repository changes. Each URL is pinned to an immutable commit and each local
download was checksum-verified.

### 1. Vector BLF — BMW E65/E66 PT-CAN / Local-CAN capture

- Source repository:
  <https://github.com/HeinrichG-V12/E65_ReverseEngineering>
- Source context: the README says the project reverse-engineers PT-CAN and
  Local-CAN against the author's BMW 760Li.
- Immutable source:
  <https://media.githubusercontent.com/media/HeinrichG-V12/E65_ReverseEngineering/762ecf84245c1bdaaf06ebb75d4bdb8f15c83498/Log1.blf>
- Source commit: `762ecf84245c1bdaaf06ebb75d4bdb8f15c83498`
- Source Git blob: `4037a38d32c177da4bb7654c37035a64cee8136b`
- Size: 3,402,392 bytes.
- SHA-256:
  `a093bf110eecbe095816f560c82cfd003bdeacc14ebb05a980f3d6790e038d5e`
- Confirmed BLF magic: `LOGG`.
- Locked python-can 4.6.1 baseline read:
  - 352,541 frames;
  - 94 identities;
  - two python-can internal channels, `0` and `1`;
  - 157.328743 seconds;
  - 5 error frames;
  - no parse exception.
- Licensing: the repository declares no license. Do not copy this file into
  the product repository or release artifacts. It is an opt-in external
  validation input only.

### 2. PCAN TRC — 2013 Kia idling capture

- Source repository:
  <https://github.com/rusefi/rusefi_documentation>
- Immutable source:
  <https://raw.githubusercontent.com/rusefi/rusefi_documentation/7b5d19ed8c30fe425d3d87e935b98f9df524d2db/OEM-Docs/Kia/2013-CAN-logs/idling.trc>
- Source commit: `7b5d19ed8c30fe425d3d87e935b98f9df524d2db`
- Source Git blob: `6df3766eae8f0b4c96452e8290542586e03ae5f0`
- Size: 271,887 bytes.
- SHA-256:
  `9dc64e4cbe47882510425c69af232c05cab5ae5af7d58e59dbc5b8c7a8db0832`
- Header evidence: PCAN trace 2.0, generated by PCAN-View 4.3.4.615,
  nominal 500 kbit/s.
- Locked python-can 4.6.1 baseline read:
  - 4,228 frames;
  - 27 identities;
  - one channel;
  - 2.529166 seconds;
  - no parse exception.
- Licensing: repository declares GPL-3.0. Keep the downloaded original outside
  this repository unless a legal review approves redistribution and the
  required notices.

### 3. candump — BYD Sealion 6 capture

- Source repository:
  <https://github.com/ROOTCONLabs/carhacking>
- Immutable source:
  <https://raw.githubusercontent.com/ROOTCONLabs/carhacking/5ea5985702daa54d4d64ae6ba314d1e11ba5f62e/canDatasets/byd_sealion_6/candump.log>
- Source commit: `5ea5985702daa54d4d64ae6ba314d1e11ba5f62e`
- Source Git blob: `edbe17836e285a72b9de3d2dab80609d1b7ad55e`
- Size: 69,736 bytes.
- SHA-256:
  `1018b3641e9bc4cca5e7bb431d16e384b0cde14fd00f459acc5a44bd5b76ea22`
- Syntax evidence: canonical absolute-timestamp candump lines such as
  `(1751639190.197433) can0 294#55005607482E04D3`.
- Locked python-can 4.6.1 baseline read:
  - 1,516 frames;
  - 5 identities;
  - channel `can0`;
  - 34.936091 seconds;
  - no parse exception.
- Licensing: the repository declares no license. Do not redistribute the file;
  use the pinned external original only for local/manual validation.

### Fixture and provenance policy

The deterministic gate must stay offline and redistributable:

1. Do not make unit or integration tests download these files.
2. Do not commit the BMW or BYD captures because their repositories grant no
   redistribution license.
3. Do not commit the Kia GPL capture without an explicit compatibility and
   notice decision.
4. Keep small deterministic fixtures in the test tree. Hand-author the text
   fixtures from public format specifications; generate the minimal BLF fixture
   with an independently reviewed known frame set and record how it was made.
5. Use the three downloaded originals in a separate, opt-in real-log
   validation command. Pin commit, size, and SHA-256 before parsing so an
   upstream replacement cannot silently change the evidence.
6. Record only aggregate validation facts in the completion record—frame
   counts, channel counts, duration, parser result—not payload dumps.

The current `/tmp` downloads are disposable. The plan contains everything
needed to reproduce them after `/tmp` is cleared.

## Architectural design

```text
Flutter Recorded log
  -> generic upload (existing)
  -> POST /api/inspect_can_log/        new, read-only
       -> iotsploit_protocols.canbus.logfile.scan_log
       -> format + channels + authoritative bounded stats
  -> target + target bus + log channel
  -> existing CAN Live Capture replay request
       -> open_log(path, channel)
            .asc -> existing AscLogReader
            .blf -> BLF adapter over python-can
            .log -> candump adapter over python-can
            .trc -> TRC adapter over python-can
       -> existing ReplayMessage stream
       -> existing CaptureAggregator / codec / timeline / observations
```

Dependency direction remains:

```text
iotsploit-django  ─┐
iotsploit-exploits ├─> iotsploit-protocols -> iotsploit-core
iotsploit-cli     ─┘
```

The Django endpoint does not parse files itself. The plugin does not grow
format branches. Both consume the protocol-layer owner.

## Reader contract and implementation decisions

### One normalized output

Every reader yields the existing `ReplayMessage` fields:

```text
timestamp
arbitration_id
data
is_extended_id
is_error_frame
is_remote_frame
is_fd
channel
```

Downstream code must not inspect a suffix or a python-can message type.

### Preserve the ASC reader

Do not route ASC through python-can. The existing reader deliberately supports
both real CAN FD column orders and applies Vector ASC-specific DLC/length rules
that are already regression-tested.

### Reuse python-can for the three new formats

Use the locked readers rather than implementing three format parsers:

- `can.io.BLFReader`;
- `can.io.CanutilsLogReader`;
- `can.io.TRCReader`.

Import them lazily when their format is opened. Convert each yielded
`can.Message` immediately into `ReplayMessage`, then close the upstream reader
on success and failure. No bus is constructed and no host CAN configuration is
read.

A focused test must prove opening each file reader never calls `can.Bus`, never
opens a SocketCAN socket, and works on a host with no CAN interface.

### Common accounting belongs beside `open_log`

Extract only the accounting genuinely shared by four readers:

- observe all source channels before filtering;
- include only the selected channel in frame/error counts and timestamps;
- stop at `max_frames` data frames and mark `truncated`;
- preserve first/last timestamps and derive duration;
- surface parser failures as `CanLogError` with filename and format;
- guarantee reader closure.

Do not introduce a general plugin system or public reader-registration API.
The existing private suffix registry is sufficient.

### Detection and refusal

Suffix selects the candidate reader, then the reader validates its own format:

- BLF: require `LOGG` and a valid BLF header;
- candump: require canonical candump record syntax, not arbitrary `.log` text;
- TRC: require a PEAK trace header/version or a valid supported legacy form;
- ASC: retain current behavior.

Unknown suffixes list `.asc`, `.blf`, `.log`, and `.trc`. A known suffix with
wrong content names the expected format. Do not fall through and try every
parser: accepting a mistaken parser is worse than a clear refusal.

### Parser errors

- Existing ASC behavior remains: malformed frame lines are counted and skipped.
- For upstream BLF/TRC/candump readers, wrap their parse exception as
  `CanLogError`; never leak `struct.error`, `ValueError`, or a python-can class
  through the plugin boundary.
- A damaged binary BLF is fatal because resynchronizing a compressed object
  stream would be a guess.
- Do not claim an exact skipped-line count for a reader that cannot report one.
  `unparsable_lines` remains zero for a clean read; a fatal format error is
  reported as an error, not disguised as a completed partial replay.

### Channel representation

Define one internal `LogChannel` value as `int | str`:

- digit-only request strings normalize to `int` for backward compatibility;
- non-empty strings remain strings for candump interfaces;
- booleans, floats, lists, maps, and empty strings are rejected;
- ASC and TRC expose their numeric channel as recorded;
- candump exposes its interface name, for example `can0`;
- BLF converts python-can's zero-based internal channel back to the source's
  one-based Vector channel before it reaches the UI or result.

Sort mixed channel values by a stable display label rather than direct Python
comparison. Keep the JSON value's scalar type so an old numeric client remains
valid.

### Multi-channel invariant

After the authoritative scan:

- zero channels: fail with “nothing parsed as CAN traffic” and format context;
- one channel and request omitted: select that sole channel automatically and
  record it in result provenance;
- several channels and request omitted: refuse and list them;
- supplied channel absent: refuse and list the channels present;
- supplied channel present: replay only that channel.

Enforce this in the replay owner, not only Flutter. CLI, API, MCP, and future
callers must get the same protection.

## HTTP contract

Add one read-only endpoint owned by `can_views.py`:

```http
POST /api/inspect_can_log/
Content-Type: application/json

{"path": "/srv/uploads/can-logs/generated-name.blf"}
```

Successful response:

```json
{
  "status": "success",
  "format": "blf",
  "channels": [1, 2],
  "frames": 352541,
  "error_frames": 5,
  "duration_s": 157.328743,
  "started_at": "...",
  "truncated": false
}
```

Rules:

- The endpoint accepts only a backend path produced by the existing upload
  workflow; use the same trust boundary currently used by replay. Do not accept
  file bytes or a client-local path.
- Use the replay frame ceiling so inspection and replay describe the same
  bounded prefix of an oversized file.
- Run the authoritative scan in the request for v1. The real 352k-frame BLF
  parsed quickly in the research check; do not add a metadata cache without a
  measured need and an invalidation design.
- Return HTTP 400 with `CanLogError` text for missing, unsupported, malformed,
  or empty files.
- Register the route and update the HTTP route contract snapshot.

`identify_can_bus` must accept the widened `log_channel` and must enforce the
same multi-channel invariant before scoring. It must never score identities
combined from several recorded buses.

## Replay request contract

The schema version remains 1:

```json
{
  "schema_version": 1,
  "bus_id": "bus_can_powertrain",
  "mode": "replay",
  "transport": {
    "interface": "file",
    "path": "/srv/uploads/can-logs/generated-name.log",
    "display_name": "road-test.log",
    "log_channel": "can0"
  },
  "max_frames": 5000000,
  "snapshot_interval_ms": 200,
  "decode": true
}
```

Numeric callers remain valid:

```json
"log_channel": 2
```

The result's transport provenance must use the reader's canonical format name,
not merely `path.suffix`, and must carry the effective channel even when a
single channel was selected automatically.

## Flutter behavior

### File selection and upload

- Allow `asc`, `blf`, `log`, and `trc`.
- Change the empty field text to `Choose an ASC, BLF, candump, or TRC log`.
- Keep pick/upload separate from replay.
- After upload, call `/api/inspect_can_log/` and keep the Open log action
  disabled until inspection succeeds.
- If inspection fails, clear the stored path/name/channel so a stale previous
  file cannot be replayed.

### Channel field

- No channels: show the inspection error.
- One channel: select it automatically and show it in the context strip; no
  extra control is needed.
- Multiple channels: insert a `Log channel` decorated dropdown between Log file
  and Decode target; require an explicit choice.
- Use display labels such as `Channel 2` for numeric values and `can0` for named
  values.
- Changing files clears the previous channel before inspection.
- Changing target or target bus does not clear the log channel: it describes
  the source file, not the decode catalogue.

### Replay and Identify bus

- Include the selected `log_channel` in the plugin transport.
- Include the same `log_channel` in `/api/identify_can_bus/`.
- Disable Open log and Identify bus when a multi-channel file has no selection.
- Include format and channel in the stable context strip, for example
  `road-test.blf · BLF · Channel 2`.
- Keep the existing replay table, timeline, scrubber, speed control, footer,
  and error banner unchanged.

No new shared component is expected. If implementation proves otherwise,
inspect the Component Showcase again and add only a genuinely reusable
component to it.

## CLI behavior

- Widen `CanLiveRun.log_channel` to `int | str | None`.
- Let `--log-channel` accept text and rely on the shared request normalization.
- Print `ch2` for numeric values and `can0` for named values.
- Interactive replay choices use the channel value returned by the reader and
  stop coercing the choice to `int`.
- Multiple channels still prompt; one channel is automatic; none fails.

No new CLI command is required.

## Files expected to change

### Root repository

| File | Required change |
| --- | --- |
| `iotsploit-protocols/src/iotsploit_protocols/canbus/logfile.py` | New readers/adapters, widened channel type, suffix+content dispatch, common accounting, format provenance, scan/channel validation |
| `iotsploit-protocols/tests/test_canbus_logfile.py` | Deterministic BLF/candump/TRC cases and cross-format equivalence |
| `iotsploit-exploits/src/iotsploit_exploits/canbus/live_capture.py` | Widen request parsing; enforce selected-channel invariant; preserve effective channel in result/timeline |
| `iotsploit-exploits/tests/test_can_live_capture.py` | Single/multi/named-channel replay, format provenance, equivalent aggregation |
| `iotsploit-django/src/iotsploit_django/view_handlers/can_views.py` | `inspect_can_log`; shared channel normalization in identify |
| `iotsploit-django/src/iotsploit_django/web/api/plugins_urls.py` | Register inspection route |
| `iotsploit-django/tests/test_can_identify_endpoint.py` | Inspection endpoint coverage plus named and multi-channel identification behavior; keep the related CAN-log HTTP contract in one existing owner |
| `iotsploit-cli/src/iotsploit_cli/can_live.py` | Widen run/channel shape and source label |
| `iotsploit-cli/src/iotsploit_cli/commands/can_commands.py` | Accept named log channels |
| `iotsploit-cli/tests/test_can_live_cli.py` | Numeric and named replay requests |
| `docs/contracts/http_routes.json` | New route snapshot |
| `docs/product-specs/can-live-capture.md` | Four formats, channel selection, boundaries, examples, limitations |
| `docs/exec-plans/active/can_recorded_log_formats_plan.md` | Progress and final validation record; move to `completed/` only after both repositories land |

Do not add a new protocol package, plugin, decoder, or replay service.

### Flutter repository

| File | Required change |
| --- | --- |
| `ui/lib/screens/tasks/components/can_screen.dart` | Picker extensions, inspect call/state, conditional channel dropdown, replay/identify payloads, context text |
| `ui/test/widget/can_screen_test.dart` | Format acceptance, inspection lifecycle, channel gating, replay and identify payloads, stale-selection clearing |

`CanCaptureViewData`, `CanReplayTimeline`, `CanCaptureView`, and
`CanTransportBar` should remain unchanged. A requested change there is a sign
that format concerns leaked past their owner and should be challenged.

## Implementation phases

### Phase 0 — Freeze external evidence and deterministic cases

1. Re-download the three pinned external files to a temporary directory.
2. Verify size and SHA-256 before opening them.
3. Record the locked-reader baseline shown in this plan.
4. Design the smallest redistributable deterministic fixtures covering fields
   the real logs do not, especially CAN FD, extended IDs, remote frames, and a
   malformed input.
5. Keep network fixtures out of the test tree and test runner.

**Exit:** all three checksums match; their provenance and non-redistribution
status are understood; deterministic fixture content is specified before
reader code changes.

### Phase 1 — Protocol reader boundary

1. Widen the channel type and centralize normalization.
2. Add lazy adapters for BLF, candump, and TRC.
3. Extend the private suffix registry.
4. Normalize upstream messages into `ReplayMessage`.
5. Share accounting/filter/budget/closure behavior without rewriting ASC.
6. Attach canonical format metadata to the reader/result.
7. Wrap all upstream errors in `CanLogError`.

**Exit:** focused protocol tests read all four formats with no socket, filter
numeric and named channels, enforce budgets, and return a stable error for
wrong suffix content and unsupported TRC/CAN XL.

### Phase 2 — Authoritative channel semantics in replay

1. Widen `transport.log_channel` parsing.
2. Validate the requested channel against the authoritative scan.
3. Auto-select exactly one channel.
4. Refuse missing selection for multiple channels.
5. Record effective channel and canonical format in transport provenance.
6. Keep timeline bucketing, aggregation, decode, and observations untouched.

**Exit:** the same normalized four-format frame sequence produces the same
rows, totals, periods, timeline, and observations; a multi-channel request can
never combine buses.

### Phase 3 — Inspection and identification HTTP

1. Add `/api/inspect_can_log/` using the protocol-layer scanner.
2. Register and contract-test the route.
3. Widen `identify_can_bus` channel handling.
4. Apply the selected channel before scoring.
5. Refuse ambiguous multi-channel scoring.

**Exit:** deterministic Django tests cover the endpoint with no network and no
real upload directory; identify scores exactly one selected channel.

### Phase 4 — CLI compatibility

1. Widen the run model and CLI argument.
2. Preserve numeric callers and add named candump channels.
3. Remove interactive `int` coercion.
4. Update CLI tests and help text.

**Exit:** CLI payload tests prove `2` and `can0` reach the same v1 transport key
without changing live capture requests.

### Phase 5 — Flutter selection flow

1. Expand picker extensions and copy.
2. Inspect after upload.
3. Add channel state and the conditional reused dropdown.
4. Gate Open log and Identify bus on successful inspection/selection.
5. Send the channel to replay and identify.
6. Clear source-owned state when a different file is chosen or inspection
   fails.
7. Display format/channel in the existing context strip.

**Exit:** widget tests cover a single-channel candump, a two-channel BLF,
inspection failure, file replacement, replay request, and Identify bus request.
No screenshot is required if the change is only one existing dropdown pattern;
if wrapping/layout changes at 1600px or below 860px, render and inspect a
throwaway golden under the Flutter testing policy.

### Phase 6 — Documentation and deterministic gates

1. Update the product specification and limitations.
2. Run focused protocol, plugin, Django, CLI, and Flutter tests.
3. Run the complete root gate:
   `tools/testing/test-python-full.sh`.
4. Run the complete nested Flutter gate:
   `tools/testing/test-flutter-full.sh`.
5. Record passed/failed/skipped/warnings/analyzer counts.

**Exit:** both full gates pass with zero new warnings or analyzer issues.

### Phase 7 — Real-log validation

Run only after deterministic tests and both full gates pass.

1. Download each pinned file to a fresh temporary directory.
2. Verify its exact SHA-256.
3. Run `scan_log` and `open_log` through the new project boundary—not directly
   through python-can.
4. Compare aggregate results to the research baseline.
5. For the BMW multi-channel BLF, replay each channel separately and prove the
   union of per-channel frame counts equals the unfiltered scan count while no
   individual replay contains the other channel.
6. Upload each file through the actual Flutter/backend workflow and verify:
   - detected format;
   - channel presentation;
   - Open log gating;
   - timeline duration/frame count;
   - clean completion without a parser error.
7. Exercise Identify bus only against an appropriate local test target. Do not
   claim meaningful decoded signals from unrelated target definitions; format
   validation is about faithful frames, timestamps, and channel isolation.
8. Delete the temporary downloads after recording aggregate results, unless a
   human explicitly asks to retain them outside version control.

Expected aggregate results after project normalization:

| File | Frames | Identities | Effective channels | Duration | Errors |
| --- | ---: | ---: | --- | ---: | ---: |
| BMW `Log1.blf` | 352,541 | 94 | Vector channels `1`, `2` after restoring source numbering | 157.328743 s | 5 |
| Kia `idling.trc` | 4,228 | 27 | channel `1` | 2.529166 s | 0 |
| BYD `candump.log` | 1,516 | 5 | `can0` | 34.936091 s | 0 |

Treat a mismatch as a defect to explain, not a number to update automatically.
If source-channel normalization intentionally changes only the BLF labels from
python-can's internal `0,1` to Vector's source `1,2`, frame counts and payloads
must remain identical.

## Deterministic test matrix

| Behavior | ASC | BLF | candump | TRC |
| --- | ---: | ---: | ---: | ---: |
| Classic standard frame | existing | add | add | add |
| Extended ID | existing | add | add | add |
| CAN FD payload and FD flag | existing | add | add | add for TRC 2.x |
| Remote frame | existing | add | add | add where supported |
| Error frame separated from traffic | existing | add | add | document reader capability |
| Absolute start time | existing | add | add | add |
| Measured inter-arrival period | existing | add | add | add |
| Multiple numeric channels | existing | add | n/a | add |
| Named channel | n/a | n/a | add | n/a |
| Selected-channel isolation | existing | add | add | add |
| Frame budget/truncation | existing | add | add | add |
| Invalid signature/header | existing suffix case | add | add | add |
| Parser exception becomes `CanLogError` | existing | add | add | add |
| No socket/config access | existing behavior | add | add | add |

Cross-format equivalence should use one small semantic traffic sequence encoded
four ways and assert normalized messages, aggregates, and periods. Keep
format-specific tests only for behavior that genuinely differs.

## Acceptance criteria

The plan is complete only when all are true:

1. Flutter accepts `.asc`, `.blf`, `.log`, and `.trc` and names them accurately.
2. The backend validates content after suffix dispatch and returns clear errors
   for mislabeled or unsupported files.
3. A multi-channel recording cannot replay or be bus-scored without one
   explicit selected channel.
4. A single-channel recording selects and records its only channel
   automatically.
5. Numeric ASC/BLF/TRC and named candump channels work through Flutter, direct
   API, interactive plugin flow, and CLI.
6. Equivalent traffic yields equivalent normalized messages, aggregates,
   measured periods, timeline states, and observations in all four formats.
7. Error and remote frames never become ordinary traffic identities.
8. The custom ASC behavior and every existing ASC regression remain unchanged.
9. Opening a recorded file performs no CAN device discovery, socket creation,
   link configuration, or transmission.
10. Unsupported TRC 3/CAN XL input is rejected explicitly rather than partially
    replayed as CAN FD.
11. Deterministic tests require no Internet, hardware, display, Redis, or live
    Django server.
12. Both complete repository gates pass.
13. The three pinned external logs pass the real-log validation with recorded
    checksums and aggregate results.
14. No external real vehicle log is committed or redistributed without an
    explicit license decision.

## Risks and controls

| Risk | Control |
| --- | --- |
| Plausible wrong decoding from mixed buses | Inspect first; explicit multi-channel selection; enforce again in replay and identify owners |
| Candump interface names rejected by numeric contract | One shared `int | str` normalization used by plugin, endpoint, and CLI |
| BLF channel labels off by one | Convert python-can internal numbering back to Vector source numbering; pin with real two-channel BLF |
| ASC regression from “unifying” readers | Keep custom `AscLogReader`; share only outer accounting |
| Parser implementation duplicated from dependencies | Use existing locked python-can readers; add only normalization/contract adapters |
| Binary parser error leaks a low-level exception | Wrap at protocol boundary as `CanLogError` with format and filename |
| New reader imports open hardware/config | Lazy import and explicit no-`can.Bus` test |
| Arbitrary `.log` accepted as candump | Validate canonical record syntax; no parser fallthrough |
| Newer TRC/CAN XL partially misread | Version/type refusal test and documented boundary |
| Real logs make CI flaky or legally unclear | Offline deterministic fixtures in gate; pinned external logs only in opt-in validation |
| Large upload exhausts UI/server memory | Existing cross-format debt; document and measure separately, do not hide it in reader work |
| Inspection adds a third parse pass | Start simple and correct; benchmark real 352k-frame BLF; add caching only from measured need |

## Sequencing and repository commits

Order is deliberate:

```text
P0 evidence
  -> P1 protocol readers
  -> P2 replay/channel invariant
  -> P3 Django inspection/identify
  -> P4 CLI
  -> root full gate + root commit
  -> P5 Flutter
  -> Flutter full gate + nested-ui commit
  -> P6 docs/final gates
  -> P7 external real-log validation
```

The root commit must land before Flutter depends on `/api/inspect_can_log/`.
During development the Flutter widget tests use a mocked endpoint, but the two
repositories must not be presented as deployable independently once the UI
starts requiring inspection.

Do not start by editing Flutter extensions. The reader and channel contracts
must be frozen first, otherwise UI work will guess response types that later
change.

## Completion record template

When implementation finishes, append:

- root commit and branch;
- nested `ui/` commit and branch;
- exact files changed and any justified deviation from this plan;
- focused test commands and counts;
- Python full-gate passed/failed/skipped/warnings counts;
- Flutter full-gate passed/failed/skipped/analyzer counts;
- each real-log URL, checksum result, scan result, replay result, and elapsed
  parse time;
- whether temporary external downloads were deleted;
- remaining limitations, especially upload buffering, MF4, TRC 3, CAN XL, and
  compressed logs;
- move this document from `active/` to `completed/` only after both commits and
  the real-log validation are complete.
