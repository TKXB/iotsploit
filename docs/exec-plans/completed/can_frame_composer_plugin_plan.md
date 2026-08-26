# Target-Aware CAN Frame Composer Plugin Plan

## Status

Accepted on 2026-08-24. **Completed 2026-08-25** — see the completion record at the end of this file.

Reviewed against the code on 2026-08-24 before implementation. Blocking
corrections from that review are folded into the sections below and marked
**Review 2026-08-24**. Non-blocking observations (facet package location,
pre-existing duplicate `doip` facet registration) were deliberately not acted
on here.

Amended 2026-08-24 to state the decode side explicitly: `decode_frame` is in
scope as the codec inverse, live capture is not. See *Scope of "parse" in v1*.

The operator selected **Option C: a dedicated Flutter signal editor with a
structured JSON fallback**. This settles the input experience. The backend uses
the previously recommended shape: reusable CAN resolution, encoding, and
SocketCAN helpers in the existing `iotsploit-protocols` package, with a thin
official plugin in `iotsploit-exploits`.

This plan covers two Git repositories in the same workspace:

- the root IoTSploit repository for Python, Django, MCP, and this plan;
- the nested `ui/` repository for Flutter.

They must be committed, reviewed, merged, and pushed independently.

## Objective

Let an operator select a CAN bus and a documented frame from the active target,
enter physical signal values, preview the exact encoded payload, and explicitly
transmit one frame through a preconfigured Linux SocketCAN interface.

The same plugin contract must remain callable without Flutter. Direct API and
MCP callers pass the structured request as a JSON object; the current CLI can
pass the same request as JSON text until it gains a structured editor.

The first version is deliberately a **one-frame composer**, not a replay or
flooding tool.

### Scope of "parse" in v1

CAN work splits into three features that share one catalogue and one codec but
have nothing else in common. This plan is the first, and adds the codec half of
the others:

| | Shape | This plan |
|---|---|---|
| Compose and send one frame | One-shot, request/response, no persistence | **In scope** |
| Decode bytes to signals | Pure function, no I/O | **In scope** — `decode_frame`, the codec inverse |
| Capture and decode live traffic | Long-running, stateful, produces observations | **Out of scope** — separate plan |

The split is not caution, it is a difference in kind. A composer is one request
that ends; a sniffer is an acquisition loop that owns a bus for minutes and
turns what it sees into durable facts. Those belong to different components:
this plugin must not start a background loop, while `SocketCANDriver` already
owns streaming and already broadcasts raw frames. Merging them would put an
acquisition loop behind a synchronous plugin call.

The receiving side also already has its destination designed. Observations
model exactly "this frame was seen on this target"; `canonical_frame_id` in the
CAN facet exists to be an observation `subject_id`; the explorer already renders
CAN message observations; and `tools/seed_can_observations.py` exists solely
because no sniffer produces them yet. A capture feature therefore has a decided
target shape and needs its own plan for scan scopes, completeness semantics,
and a monitor UI — not a section bolted onto a send dialog.

That plan is `can_live_capture_plan.md`, drafted alongside this one. It consumes
this plan's catalogue, definitions, and `decode_frame` unchanged, and must not
start before phase 2 here exits — otherwise the same definitions get a second
resolver and a second codec.

Decoding a stored capture file (candump/BLF/ASC to decoded rows) is a third
feature again. It reuses this plan's catalogue and `decode_frame` unchanged and
needs no hardware, which is exactly why the codec is written here.

## User-visible result

The Plugins page and Control Panel open the same target-aware composer for the
new plugin:

```text
Target:  Bench Vehicle                       status: active
Bus:     Powertrain CAN
Frame:   VehicleStatus                 ID: 0x123 · CAN 2.0 · DLC 8
Channel: can0

Signal                 Value                         Unit
VehicleSpeed           42.5                          km/h
IgnitionState          On
AliveCounter           3                             0..15

Payload preview: 03 00 A9 01 00 00 00 00

[Encode only]                             [Transmit one frame]
```

The editor never computes the authoritative payload in Dart. It sends a preview
request to the plugin, displays the Python result, and sends only after a second
explicit confirmation.

## Current implementation facts

### Target and CAN data

- Plugin execution normalizes the selected target into a dictionary snapshot
  in `iotsploit_core.core.exploit_manager`.
- ARXML frames and transmitter-less DBC frames live under
  `bus.properties.messages`.
- Transmitter-attributed DBC frames live under
  `component.facets.can.messages`, with the facet's `bus_id` naming the bus.
- A frame's wire identity is `(bus_id, frame_id, is_extended)`. A name alone is
  not an identity, and the same name or numeric ID may legitimately occur on
  another bus.
- Bus-owned messages are untyped JSON under `bus.properties`, so they keep
  whatever the ARXML importer wrote: start bit, length, byte order, signedness,
  factor, offset, range, unit, choices, `is_fd`, `multiplexer`,
  `multiplexer_signal`, and `contained_messages`.
- **Review 2026-08-24 — component-owned messages do not.** The CAN facet models
  in `iotsploit-django/src/iotsploit_django/tools/can_facet.py` are narrower
  than the bus-owned JSON:
  - `CanSignal` has no `choices`, no `multiplexer_signal`, and no float/decimal
    encoding metadata;
  - `CanMessage` has no `is_fd`, `senders`, `cycle_time_ms`, or
    `contained_messages`;
  - both are plain `BaseModel`, so pydantic's default `extra="ignore"` applies
    and unknown keys are dropped on load. This is unlike `Facet` itself, which
    sets `extra="allow"` precisely to survive that round trip.
  Until this is corrected, a component-owned frame cannot express a value table
  or CAN-FD, and "bus-owned and component-owned frames resolve identically" is
  not achievable. See *Signal semantics*.
- **Review 2026-08-24** — `iotsploit-django/src/iotsploit_django/tools/dbc.py`
  parses `SG_` lines only and never reads `VAL_`, so DBC import produces no
  choices at all regardless of the facet schema.
- Large targets contain hundreds of frames and thousands of signals. The list
  endpoint intentionally returns summaries; the composer must fetch one full
  target with `TargetsService.getTarget()` only when it opens.

### Plugin input and execution

- `BasePlugin` metadata declares a `Parameters` map.
- The Plugins page and Control Panel each implement a separate generic
  parameter dialog.
- Both dialogs treat `int` specially and coerce every other type to text. They
  do not render object values, choices, units, ranges, or target-dependent
  selectors.
- `PluginService.executePlugin()` already serializes nested Dart maps to JSON,
  so no new transport envelope is needed for structured parameters.
- `/api/execute_plugin/` currently acts on a process-global current target. The
  request does not identify the target that Flutter used to build its form.
  That race is tolerable for read-only utilities and unacceptable for hardware
  transmission.

### CAN transport

- `cantools` 42.0.3 is already an `iotsploit-protocols` dependency and is the
  source of truth for ARXML CAN layouts.
- `python-can` 4.x is already used by `iotsploit-drivers`.
- The existing `SocketCANDriver` owns discovery, interface setup, streaming,
  and a stateful bus. Its send helper now takes extended and FD flags, and it
  reads link configuration from the kernel instead of assuming 500 kbit, but it
  remains a stateful singleton with an acquisition thread. The composer must
  still not call it or instantiate a device driver behind the plugin manager.
- SocketCAN link state and bitrate are host configuration. The new client must
  not invoke `sudo`, run `ip link`, or silently configure an interface.
- **Review 2026-08-24 — a SocketCAN device plugin already exists and no second
  one is needed.** `drv_socketcan` is registered as a packaged device-driver
  entry point, and `ui/lib/screens/tasks/components/can_screen.dart` already
  drives it: it lists CAN devices, streams them over the device WebSocket, and
  sends raw `id` + `data` frames through
  `/api/execute_device_command/drv_socketcan/`. That screen keeps its role as
  the raw monitor/send tool; the composer is the target-aware path. Neither
  replaces the other in v1.
- **Review 2026-08-24 — why the composer still does not transmit through that
  driver.** Its send helper cannot express the required frame (no extended
  send timeout, and no preview); its lifecycle may still bring a link up with
  `sudo` when the operator has not configured one; and it is a singleton with
  one bus and a running acquisition thread, so borrowing it either injects
  privileged link mutation into the composer or introduces a second mutable
  "current device" race on top of the current-target race this plan removes.
  SocketCAN permits several sockets on one interface, so the one-shot client
  and the driver's monitor coexist without contention.
- **Review 2026-08-24 — the physical channel comes from driver discovery.** The
  device driver's scan is the only inventory of usable interfaces. The channel
  a composer sends is `SocketCANDevice.interface` (`can0`), not the driver's
  `device_id` (`can_001`); confusing the two produces a channel name that
  cannot be opened.
- **Review 2026-08-24** — `python-can` is wrapped in two other places already:
  `iotsploit-fuzzer/src/iotsploit_fuzzer/interfaces/can_interface.py` (a fuzz
  harness sink that hardcodes an arbitration ID and sets bitrate at open) and
  the fuzzer protocol adapters in `iotsploit-django/src/iotsploit_django/tools`
  (session-scoped interface/bitrate configuration). Neither sends a
  target-defined frame; the composer does not reuse or refactor them in v1.

## Decisions

| # | Decision | Chosen behavior | Reason |
|---|---|---|---|
| 1 | Product input | Dedicated Flutter composer | A signal map is not usable as one generic text field. |
| 2 | Non-Flutter input | The same versioned JSON request | No second plugin contract for MCP or CLI. |
| 3 | Encoding authority | Python `cantools`, strict mode | Big-endian and multiplexed packing must not be reimplemented in Dart. |
| 4 | Definition lookup | Bus-owned and component-owned frames | Both ARXML and DBC target shapes must work. |
| 5 | Frame identity | Bus ID + numeric ID + extended flag; name is a stale-data check | Prevent cross-bus and standard/extended ambiguity. |
| 6 | Transport | One-shot explicit SocketCAN client in `iotsploit-protocols` | Matches existing explicit SOME/IP/DoIP clients without adding a new package. |
| 7 | Device lifecycle | Interface is already configured and up | A send plugin must not alter host networking or require `sudo`. |
| 8 | Safety flow | Preview, then confirmed transmit | The operator sees the exact bytes before hardware mutation. |
| 9 | Repetition | Exactly one frame per transmit request | Cyclic send and flooding require separate controls and review. |
| 10 | Draft target | Preview allowed; transmit needs an explicit override | An ECU extract is not proof of complete vehicle topology. |
| 11 | Target selection | Optional `target_id` in execute-plugin transport; required from Flutter | Avoid the mutable-current-target race while preserving old callers. |
| 12 | Observations | Do not create observations | Sending is an action, not evidence that a target emitted or accepted a frame. |
| 13 | UI reuse | One shared parameter/composer implementation | Plugins and Control Panel must not drift again. |
| 14 | Containers | Reject AUTOSAR container frames in v1 | Header selection and contained-PDU encoding need a separate design. |
| 15 | Device plugin role | Existing `drv_socketcan` supplies channel discovery only; it never carries the composer's transmit | Its send helper cannot express the frame, and its lifecycle is privileged, stateful, and shared. |
| 16 | Channel input | Operator picks an interface from the device-driver scan; free text is a fallback, never the default | A mistyped channel is either an unopenable name or the wrong physical bus. |

## Architecture

```text
Flutter full target
  -> local searchable CAN catalogue (display only)
  -> structured request + explicit target_id
  -> Django resolves that exact target
  -> CAN Frame Composer plugin
       -> target catalogue resolver
       -> cantools strict encoder
       -> preview result + digest
  -> Flutter preview and danger confirmation
  -> same request + preview digest + operation=transmit
  -> resolve and encode again
  -> digest comparison
  -> one python-can SocketCAN send
```

Dependency direction remains inward:

```text
iotsploit-exploits -> iotsploit-protocols -> iotsploit-core
iotsploit-django  -> iotsploit-core
Flutter           -> HTTP contract only
```

Neither `iotsploit-core` nor the plugin imports Django. No new core port is
needed for a short-lived explicit protocol client. Stateful acquisition remains
the device driver's responsibility.

## Plugin contract

### Metadata

Register one packaged entry point:

```toml
can_frame_composer = "iotsploit_exploits.canbus.frame_composer:CanFrameComposerPlugin"
```

Its public metadata is:

```python
{
    "Name": "CAN Frame Composer",
    "Description": "Encode target-defined signals and optionally send one SocketCAN frame.",
    "RequiresRoot": False,
    "Interactive": False,
    "Parameters": {
        "request": {
            "type": "target_can_frame",
            "schema_version": 1,
            "required": True,
            "description": "Target CAN frame, signal values, transport, and operation."
        }
    }
}
```

`Interactive` stays false. The input is known before execution and belongs in
the initial parameter surface, not the durable mid-execution prompt broker.

### Execute-plugin request

Flutter sends the target identity at the execution boundary and a versioned
composer request inside plugin parameters:

```json
{
  "plugin_name": "CAN Frame Composer",
  "target_id": "bench_vehicle",
  "parameters": {
    "request": {
      "schema_version": 1,
      "operation": "preview",
      "frame": {
        "bus_id": "bus_can_powertrain",
        "frame_id": 291,
        "is_extended": false,
        "name": "VehicleStatus"
      },
      "signals": {
        "VehicleSpeed": "42.5",
        "IgnitionState": "On",
        "AliveCounter": "3"
      },
      "transport": {
        "interface": "socketcan",
        "channel": "can0",
        "timeout_ms": 1000
      },
      "allow_draft_target": false
    }
  }
}
```

Signal values are allowed to be JSON numbers or strings. Flutter sends edited
numeric values as strings so integers wider than 53/64 bits and authored
decimal text are not rounded by Dart before Python validates them.

The `request` value may also be a JSON string containing the same object. This
is the compatibility path for the current CLI, whose unknown parameter types
fall back to text input. The plugin normalizes object-or-string once at its
boundary and uses one validation path afterwards.

Programmatic callers should send the object form.

### Preview result

Successful preview returns an `ExploitResult` whose data has this stable shape:

```json
{
  "operation": "preview",
  "target": {
    "target_id": "bench_vehicle",
    "status": "active"
  },
  "bus": {
    "bus_id": "bus_can_powertrain",
    "name": "Powertrain CAN"
  },
  "frame": {
    "name": "VehicleStatus",
    "frame_id": 291,
    "frame_id_hex": "0x123",
    "is_extended": false,
    "is_fd": false,
    "dlc": 8,
    "data_hex": "0300A90100000000"
  },
  "signals": {
    "VehicleSpeed": 42.5,
    "IgnitionState": "On",
    "AliveCounter": 3
  },
  "transport": {
    "interface": "socketcan",
    "channel": "can0",
    "timeout_ms": 1000
  },
  "preview_digest": "sha256:...",
  "warnings": []
}
```

The result contains normalized values, not merely an echo of operator text.
Errors return `success=false`, a concise message, and structured data where it
helps the editor:

```json
{
  "field_errors": {
    "signals.VehicleSpeed": "must be between 0 and 250 km/h"
  }
}
```

### Transmit request and result

The transmit request is the preview request with:

```json
{
  "operation": "transmit",
  "preview_digest": "sha256:..."
}
```

The plugin resolves the current target snapshot and re-encodes the request. It
refuses to send if the recomputed digest differs. The digest covers:

- schema version;
- target ID and status;
- bus ID;
- frame identity and complete definition relevant to encoding;
- normalized signal values;
- encoded bytes and CAN flags;
- SocketCAN interface and channel.

**Review 2026-08-24.** The digest must be computed over a canonical
serialization with sorted keys and a fixed numeric representation. A digest
taken over incidental dict ordering compares unequal for an unchanged request,
which turns the consistency guard into an intermittent refusal to transmit.

The digest is a consistency guard, not authorization and not a one-time token.
Repeating an explicitly confirmed API call can send another frame. Authentication
and rate limiting belong to the platform-wide safety gate, which is outside this
feature.

A successful transmit adds:

```json
{
  "operation": "transmit",
  "sent": true,
  "sent_at": "2026-08-24T...Z"
}
```

## Target catalogue resolution

Implement a pure resolver that accepts a target mapping and never reads the
database or current target.

### Collection algorithm

For the requested CAN bus:

1. Find exactly one `buses[*]` row matching `bus_id` and require `type == "can"`.
2. Collect mappings from `bus.properties.messages`.
3. For each component, inspect `facets.can` and collect its messages only when
   `facets.can.bus_id` equals the requested bus.
4. Attach source metadata for display and diagnostics:
   `owner_kind` (`bus` or `component`), component ID/name where applicable,
   senders, and the original list index.
5. Group by `(frame_id, is_extended)`.
6. Deduplicate byte-for-byte-equivalent definitions.
7. If definitions sharing one identity disagree on DLC, layout, scaling,
   multiplexing, or CAN-FD state, mark the frame conflicted. The UI may display
   it, but preview and transmit must fail rather than choose one silently.
8. Match the request by ID and extended flag. Treat the supplied name as a
   stale-form check; fail if the resolved definition has a different name.

Frame IDs must be integers in the correct range:

- standard: `0..0x7FF`;
- extended: `0..0x1FFFFFFF`.

The resolver returns immutable protocol-layer definitions. It must not mutate
the target snapshot.

### Supported messages

V1 supports ordinary classic CAN and CAN-FD messages whose payload length is
valid for the corresponding frame type.

Reject with a clear reason when:

- `contained_messages` is non-empty;
- DLC or a signal crosses the payload boundary;
- multiplexing metadata is incomplete or contradictory;
- two definitions conflict;
- the selected bus, frame, or signal no longer exists;
- an extended flag does not match the target definition.

### Signal semantics

- Operator values are physical values by default.
- Named choices are accepted exactly as stored; raw numeric choice codes also
  remain valid.
- Byte order maps `little` to `little_endian` and `big` to `big_endian`.
- Signedness, factor, offset, minimum, maximum, unit, and multiplexer metadata
  are reconstructed into `cantools` objects.
- The multiplexer value must be present before branch signals are resolved.
- Every common signal and every signal active for the selected branch must be
  supplied. Unknown or inactive-branch values are errors.
- No unspecified signal is silently filled with zero, minimum, or an inferred
  default.
- Strict `cantools.Message.encode(..., scaling=True, strict=True)` is the final
  validator and encoder.

Target signal definitions must carry every lossless field required to
reconstruct the installed `cantools` message. **Review 2026-08-24 — this is a
blocking prerequisite for component-owned frames, not a refinement.** Phase 2
must, in `iotsploit-django/src/iotsploit_django/tools/can_facet.py`:

- add `choices` and `multiplexer_signal` to `CanSignal`, plus the float/decimal
  encoding metadata needed when the source provides it;
- add `is_fd` to `CanMessage`, and `contained_messages` at least well enough to
  detect and reject a container frame (see *Supported messages*);
- set `extra="allow"` on both models, so a field written by a newer importer is
  not silently discarded on load the way it is today.

`iotsploit-django/src/iotsploit_django/tools/dbc.py` must read `VAL_` tables for
choices to exist on DBC-imported frames at all. Value tables it cannot attach
to a known signal are dropped with a warning, not guessed.

These are additive target JSON changes. Old targets with ordinary integer
signals remain valid, and a frame whose source never supplied a field is not
invented into existence — it simply keeps the smaller definition.

Automatic checksum, CRC, rolling-counter, freshness, SecOC, or OEM algorithm
generation is out of scope. If those fields are ordinary documented signals,
the operator supplies them. If an algorithm is required, preview fails until a
separate algorithm-provider design exists.

## Protocol-layer design

Add an `iotsploit_protocols.canbus` namespace. Intended public API:

```python
catalog = TargetCanCatalog.from_target(target)
definition = catalog.resolve(bus_id, frame_id, is_extended, expected_name=name)
encoded = encode_frame(definition, signal_values)
signals = decode_frame(definition, encoded.data)

with SocketCanClient(SocketCanConfig(channel="can0", timeout=1.0)) as client:
    client.send(encoded)
```

The concrete names may change during implementation, but the separations may
not:

- catalogue resolution is pure target-to-definition logic;
- encoding is pure definition-and-values-to-bytes logic;
- decoding is its exact inverse, pure definition-and-bytes-to-values logic;
- SocketCAN is explicit I/O behind a small client;
- the exploit plugin owns request validation, preview digest, and policy.

### Decoding

`decode_frame` ships in v1 **as a codec function, not as a capture feature.**
The reconstructed `cantools` message that encodes is the same object that
decodes, so the inverse costs one function and one code path, and withholding
it would mean writing it again elsewhere against a second reconstruction of the
same definitions.

What it buys immediately is evidence: an encode/decode round trip over every
fixture — big-endian, signed, scaled, choice, multiplexed, wide, FD — proves bit
placement in a way a hand-written golden vector cannot, because a vector and a
mistaken encoder can agree while both are wrong about the layout.

Decoding is not merely encoding backwards, and these differences are its
requirements:

- the multiplexer branch is selected **from the received bytes**, never from a
  caller's claim about which branch it is;
- named choices decode to their labels, with the raw value preserved alongside,
  so a code absent from the value table is reported rather than lost;
- a payload shorter or longer than the definition's DLC is a stated mismatch,
  not a silent truncation or pad;
- bits covered by no signal are ignored, not an error — unlike encoding, where
  an unknown signal name is an error;
- decoding never raises for ordinary bad data. Undecodable input returns a
  described failure, because the input comes from a wire and is not trusted.

`decode_frame` performs no I/O, opens no bus, and records no observation. What
uses it beyond round-trip tests in v1: the preview response may show the
decoded read-back of the bytes it just encoded, which is a genuine check that
what the operator typed is what the frame says.

`SocketCanClient` requirements:

- use `python-can` with `interface="socketcan"` and `ignore_config=True`;
- validate the Linux channel name before opening it;
- never configure bitrate or link state;
- construct `can.Message` with target-derived arbitration ID,
  `is_extended_id`, `is_fd`, DLC/data, and `check=True`;
- use the configured send timeout;
- always call `shutdown()` in `__exit__`, including after errors;
- translate `python-can` exceptions into protocol-layer errors with no Django
  dependency;
- import or open transport lazily so preview works on hosts without a usable
  SocketCAN interface.

## Plugin behavior

`CanFrameComposerPlugin.execute(target, parameters)` is synchronous and has no
streaming or duration parameter, so the manager does not route it to Celery.

**Review 2026-08-24 — `RequiresRoot` must stay false, and that is load-bearing.**
The root path in `plugin_views.py` does not hand the sudo runner a full target;
it reduces the target to name, IP, type, description, and ID. A composer marked
`RequiresRoot: True` would therefore receive a snapshot with no `buses` and no
`components`, and every frame lookup would fail as "bus not found" rather than
as a configuration error. Nothing in this plugin needs root: the interface is
already up, and sending on an up interface is unprivileged.

Execution steps:

1. Require a target dictionary with `target_id`.
2. Parse and version-check `parameters.request`.
3. Resolve the requested target frame.
4. Normalize signal values without losing integer precision.
5. Encode strictly.
6. Build the canonical response and preview digest.
7. For `preview`, return without importing/opening SocketCAN.
8. For `transmit`, require a matching digest.
9. If target status is not `active`, require `allow_draft_target=true`.
10. Open one SocketCAN client, send one message, close it, and return.

The plugin must not:

- look up `TargetManager` or any Django model;
- infer a physical channel from the AUTOSAR/DBC bus name;
- accept arbitrary `data_hex` as a substitute for target signals;
- start a background loop;
- retry a failed send automatically;
- record a transmit as an observation;
- log the complete request at info level before validation.

Audit logging for a successful transmit may include target ID, logical bus ID,
frame ID, flags, physical channel, payload hex, and outcome. It must not claim
that the ECU received or acted on the frame.

## Exact target selection at execution

Extend the existing execute-plugin transport with a backward-compatible
optional top-level `target_id`.

When present, Django must:

1. load that exact stored target;
2. return 404 if it does not exist;
3. pass its hydrated snapshot to the plugin;
4. not change the process-global current target as a side effect.

When absent, existing callers retain the current-target behavior.

**Review 2026-08-24 — the existing view already mutates current target, so an
added lookup is not sufficient.** `execute_plugin` today, when no current target
is set, picks the first vehicle target and calls `set_current_target()` on it
before running anything. The explicit path must branch **before** that
auto-select block and skip it entirely; otherwise a request that names its own
target still rewrites global state for every other client, and requirement 4
above is silently unmet. This is why the phase 4 exit criterion is tested with
no current target set, not merely with a different one selected.

Add a read method on `TargetManager` for one target ID instead of repeating
linear `get_all_targets()` scans in views. The method returns the full folded
target shape and has no mutation side effect.

Flutter always sends `target_id`. Add the same optional argument to the MCP
`execute_plugin` tool; this changes no tool count and lets agents avoid a
separate global `select_target` mutation. Existing MCP calls remain valid.

The plugin still verifies that the supplied target snapshot's ID is the one
covered by the preview digest.

## Flutter design

### Shared parameter entry point

Replace the duplicated `_showParameterDialog` / `_promptParameters` logic with
one shared plugin-parameter coordinator used by:

- `lib/screens/plugins/plugins_page.dart`;
- `lib/screens/control_center/control_center_screen.dart`.

For ordinary metadata types, behavior must remain compatible. For
`type == "target_can_frame"`, the coordinator opens the dedicated composer.

Do not hardcode the plugin name. Dispatch on the declared parameter type so a
future official or third-party plugin can reuse the composer contract.

### Data model

Add a pure Dart catalogue/index over the decoded full target. It mirrors the
backend's two storage locations and frame identity rules for display, but is
never authoritative for sending.

Do not create a second divergent CAN traversal. Extract or delegate the
existing CAN indexing in `TargetModel` so the explorer and composer share the
same bus-owned/component-owned enumeration rules.

The Dart model should expose typed immutable view models for:

- CAN buses;
- frame identity and owner/source labels;
- signals, ranges, units, choices, and multiplexing;
- conflict/unsupported reasons;
- target status and provenance warnings.

Keep signal entry text as strings until the backend response normalizes it.

### Composer state machine

Use explicit states:

```text
loadingTarget
  -> choosingFrame
  -> editingSignals
  -> previewing
  -> previewReady
  -> transmitting
  -> transmitted | failed
```

Changing the target, bus, frame, channel, multiplexer, or any signal after a
preview invalidates and removes the preview digest. A disabled Transmit button
must make stale previews impossible to send accidentally.

Closing the dialog during preview/transmit must not call `setState` after
dispose. HTTP completion may be ignored by the closed view, but the backend
result remains authoritative.

### Bus and frame selection

- Require a selected target before opening the composer.
- Fetch the full target only on open; show loading and retry states.
- List only `type == "can"` buses.
- Search frames by name, decimal ID, and hex ID.
- Display canonical standard/extended ID, DLC, CAN-FD badge, and source owner.
- Keep standard and extended frames with the same numeric ID separate.
- Show conflicted and unsupported definitions as disabled rows with the reason.
- Use lazy/virtualized lists; never materialize every signal widget for every
  frame in the target.

**Review 2026-08-24 — channel selection.** The physical channel is chosen from
the CAN devices reported by the existing device-driver scan, the same list
`can_screen.dart` already renders, not typed as free text. Send the device's
`interface` (`can0`), never its `device_id` (`can_001`). When the scan returns
nothing, say that no CAN interface was found and how to bring one up, and allow
a manual entry only as an explicit fallback. Selecting a device here must not
initialize, connect, or otherwise touch the driver: the composer reads the
inventory and nothing more.

### Signal editor

Render only the selected frame's common signals and active multiplexed branch:

- multiplexer first;
- named choices as a dropdown/searchable choice control;
- one-bit choice/boolean signals as a compact choice control when labels permit;
- numeric and scaled signals as text fields with unit and authored/derived
  range hints;
- signed and wide integers as text, not Dart `int` coercion;
- required/error state per signal;
- signal name, bit layout, factor/offset, and source details in an optional
  disclosure rather than the primary row.

The editor may provide client-side validation for fast feedback, but backend
validation is authoritative. Map backend `field_errors` back to their signal
rows.

All active signals are required in v1. Do not invent zero defaults. Preserve
entered values when a user temporarily changes search text; discard branch
values when the multiplexer changes to a branch where they are invalid, with a
clear notice.

### Preview and confirmation

`Encode only` sends `operation=preview` and displays:

- target and logical bus;
- frame name and ID;
- classic/FD and standard/extended flags;
- DLC;
- normalized signals;
- payload hex grouped by byte;
- warnings, including draft/incomplete target status.

`Transmit one frame` is disabled until preview succeeds. Pressing it opens a
danger confirmation using shared components demonstrated in the Component
Showcase. The confirmation repeats the physical channel, target, bus, frame ID,
and payload. It must say that transmission changes external hardware state and
that success means the local socket accepted the frame, not that an ECU acted
on it.

For a non-active target, add a separate explicit acknowledgement that sets
`allow_draft_target=true`; never derive that flag merely from opening the
dialog.

After send, show a durable result in the calling screen's existing execution
surface. Do not leave the button enabled while the request is in flight.

### Responsive and accessible behavior

- Use a wide dialog/side sheet on desktop and a full-height surface on narrow
  layouts.
- Keep bus/frame selectors and the send controls visible while the signal list
  scrolls.
- Reuse theme colors and shared buttons; add no hardcoded status colors.
- Every icon-only action needs a tooltip and semantic label.
- Keyboard traversal must follow bus, frame, channel, signals, preview, send.
- Error text must not rely on color alone.
- If a new reusable composer component is introduced, add it to the Component
  Showcase as required by `ui/AGENTS.md`.

## Files expected to change

Names are implementation targets, not permission to create another package.

### Root repository

| File | Change |
|---|---|
| `iotsploit-protocols/pyproject.toml` | Add `python-can`, pinned to the same range `iotsploit-drivers` already uses (`>=4.5`). |
| `iotsploit-protocols/src/iotsploit_protocols/canbus/__init__.py` | Public CAN composer API. |
| `.../canbus/catalog.py` | Resolve both target storage shapes and conflicts. |
| `.../canbus/codec.py` | Rebuild cantools definitions; encode strictly and decode as the inverse. |
| `.../canbus/socketcan.py` | Explicit one-shot SocketCAN client. |
| `iotsploit-protocols/tests/test_canbus_catalog.py` | Target resolution cases. |
| `iotsploit-protocols/tests/test_canbus_codec.py` | Bit layout, validation vectors, and encode/decode round trips. |
| `iotsploit-protocols/tests/test_socketcan_client.py` | Mocked transport flags/lifecycle. |
| `iotsploit-exploits/src/iotsploit_exploits/canbus/__init__.py` | Plugin namespace. |
| `.../canbus/frame_composer.py` | Request policy, preview digest, one-shot send. |
| `iotsploit-exploits/tests/test_can_frame_composer.py` | Plugin preview/transmit behavior. |
| `iotsploit-exploits/pyproject.toml` | Register the entry point. |
| `iotsploit-django/src/iotsploit_django/adapters/django/target_models.py` | Add side-effect-free exact target lookup on `TargetManager`. |
| `iotsploit-django/src/iotsploit_django/view_handlers/target_views.py` | Point the existing `get_target` scan at the new lookup instead of leaving a duplicate. |
| `iotsploit-django/.../plugin_views.py` | Accept optional exact `target_id`, branching before the current-target auto-select. |
| `iotsploit-django/src/iotsploit_django/tools/can_facet.py` | Add `choices`, `multiplexer_signal`, float metadata, `is_fd`, container detection; allow extra fields. |
| `iotsploit-django/src/iotsploit_django/tools/dbc.py` | Parse `VAL_` tables so DBC-imported signals can carry choices. |
| `iotsploit-django/tests/test_plugin_execution_endpoint.py` | Exact-target and compatibility contract. |
| `iotsploit-mcp/src/iotsploit_mcp/tools/write.py` | Optional `target_id` on existing tool. |
| `iotsploit-mcp/tests/test_write_tools.py` | MCP payload contract. |
| `iotsploit-protocols/src/iotsploit_protocols/autosar/arxml.py` | Preserve any remaining lossless signal fields the importer currently drops. |
| `poetry.lock` | Lock dependency changes. |
| `docs/product-specs/can-frame-composer.md` | Operator/API guide and safety semantics. |

### Flutter repository

| File | Change |
|---|---|
| `lib/services/plugin_service.dart` | Optional target ID and structured sync-result handling. |
| `lib/services/targets_service.dart` | Reuse existing full-target fetch; no new endpoint. |
| CAN device listing for the channel selector | Read the existing `/api/list_devices/` endpoint, as `can_screen.dart` already does inline; no new endpoint, and no device initialize/connect call. |
| `lib/models/can_frame_composer.dart` | Pure target CAN index and form state types. |
| `lib/widgets/plugins/plugin_parameter_dialog.dart` | Shared metadata dispatch for both screens. |
| `lib/widgets/plugins/can_frame_composer.dart` | Target-aware editor, preview, and confirmation. |
| `lib/screens/plugins/plugins_page.dart` | Replace local generic dialog with shared flow. |
| `lib/screens/control_center/control_center_screen.dart` | Replace duplicated generic dialog with shared flow. |
| `lib/screens/targets/explorer/explorer_model.dart` | Delegate shared CAN enumeration instead of duplicating it. |
| `lib/screens/component_showcase/component_showcase_page.dart` | Demonstrate reusable composer pieces if new. |
| `test/unit/can_frame_composer_model_test.dart` | Indexing, multiplexing, and precision behavior. |
| `test/unit/plugin_service_test.dart` | Request/response JSON contract. |
| `test/widget/can_frame_composer_test.dart` | Complete editor state and validation. |
| Existing Plugins/Control Panel widget tests | Both entry points use the same flow. |

Avoid editing Django templates or building a second CAN-specific API endpoint.
The target endpoint and plugin endpoint already carry the required data.

## Implementation phases

### Phase 1: Freeze contracts with tests

1. Add realistic small target fixtures covering:
   - a bus-owned ARXML-shaped frame;
   - a component CAN-facet frame;
   - the same numeric ID on two buses;
   - standard and extended variants of one numeric ID;
   - a simple multiplexed frame;
   - a conflicting duplicate definition;
   - a CAN-FD frame.
2. Write request/response contract tests before implementation.
3. Record the v1 request schema and error keys in the product guide.

Exit: failures describe the missing behavior rather than implementation names.

### Phase 2: Pure catalogue and encoder

1. Widen the CAN facet models and DBC import first, per *Signal semantics*:
   nothing downstream can resolve a component-owned frame with choices or FD
   until the stored shape can hold them.
2. Implement immutable target CAN definitions.
3. Resolve both storage locations and conflicts.
4. Reconstruct cantools conversions, choices, and multiplexing.
5. Preserve any remaining signal metadata in the ARXML import path.
6. Encode strict physical values and return canonical normalized data.
7. Implement `decode_frame` against the same reconstructed definitions.

Exit: all classic, extended, FD, endian, signed, scaled, choice, multiplexed,
wide-value, missing-value, range, and conflict tests pass with no socket import
or I/O, and every fixture survives an encode/decode round trip.

### Phase 3: SocketCAN client and thin plugin

1. Implement the explicit client with injected/mockable bus construction.
2. Implement object-or-JSON request normalization.
3. Implement preview responses and deterministic digest.
4. Implement policy gates and exactly one transmit.
5. Register the plugin entry point.

Exit: preview cannot open a bus; transmit cannot occur without a matching
preview digest; transport flags and shutdown behavior are asserted with fakes.

### Phase 4: Exact target execution contract

1. Add side-effect-free target lookup by ID.
2. Accept optional `target_id` in Django execute-plugin requests.
3. Preserve absent-ID behavior for existing clients.
4. Pass target ID from Flutter and optionally MCP.
5. Update contract tests and documentation.

Exit: two clients selecting different targets cannot cause the composer to act
on the wrong one, and existing execute-plugin tests remain compatible.

### Phase 5: Shared Flutter input architecture

1. Extract the duplicated generic parameter collection.
2. Add metadata-type dispatch.
3. Add/reuse the pure target CAN catalogue model.
4. Keep all existing plugin forms behaviorally unchanged.

Exit: both screens use one path; ordinary plugin widget tests still pass.

### Phase 6: Composer UI and preview/send flow

1. Implement lazy target loading and retry.
2. Implement bus/frame search and source/conflict display.
3. Implement typed signal rows and multiplexer behavior.
4. Implement preview rendering and digest invalidation.
5. Implement draft warning and danger confirmation.
6. Implement transmitted/error states and component showcase coverage.

Exit: widget tests exercise the complete state machine without a real backend
or CAN interface.

### Phase 7: Documentation and validation

1. Write the product guide with Flutter, direct API, MCP, and CLI JSON examples.
2. Document how to configure `vcan0`/`can0` outside IoTSploit without embedding
   privileged setup in the plugin.
3. Run both full commit gates.
4. Perform an optional manual `vcan0` check only after the deterministic suite
   passes.
5. Commit and merge root and Flutter repositories independently.

Exit: all acceptance criteria below are evidenced, or the plan remains active
with the unmet item recorded.

## Testing requirements

### Protocol catalogue and codec

- Bus-owned and component-owned frames resolve identically, including a frame
  carrying named choices and a CAN-FD frame. This must be asserted against a
  facet that has been round-tripped through the stored model, not against a
  hand-built dict, so a field the model drops fails the test.
- Frames from the wrong bus are never considered.
- Same ID across buses is not ambiguous once bus ID is supplied.
- Standard and extended forms remain distinct.
- Identical duplicates deduplicate; conflicting duplicates fail.
- Little-endian and Motorola/big-endian known vectors encode exactly.
- Every fixture round-trips: encode then decode returns the physical values that
  were encoded, for classic, extended, FD, signed, scaled, choice, and
  multiplexed frames.
- Decode selects the multiplexed branch from the payload bytes alone.
- A choice code absent from the value table decodes to the raw number with a
  stated reason, not to a fabricated label or an exception.
- A payload whose length disagrees with the definition reports the mismatch.
- Undecodable bytes return a described failure rather than raising.
- Signed min/max and off-by-one values validate.
- Factor/offset physical values round-trip through cantools.
- Named and numeric choices encode to the same raw value.
- Simple multiplexing requires the selector and only the active branch.
- Missing, extra, inactive, and misspelled signal names fail.
- Wide integers supplied as strings are not rounded.
- Classic and FD payload lengths validate.
- Container messages fail with a stable unsupported reason.

### SocketCAN client

- Preview tests never instantiate a bus.
- Standard, extended, and FD flags reach `can.Message` correctly.
- Arbitration and payload validation uses `check=True`.
- Timeout reaches `bus.send`.
- `shutdown()` runs after success and after send failure.
- Invalid channel names fail before opening a bus.
- Missing/unavailable SocketCAN reports a configuration error, not a traceback.

Use a fake bus factory. Deterministic tests must never open `can0`, `vcan0`, a
network socket, or physical hardware.

### Plugin

- Object and JSON-string request forms normalize identically.
- Unknown schema versions fail.
- Preview returns bytes, normalized signals, warnings, and digest.
- Preview has no transport side effect.
- The digest is stable across two previews of the same request built with
  different key ordering, and changes when any covered field changes.
- Missing or changed digest blocks transmit.
- Active target transmits one frame.
- Draft target blocks by default and accepts only explicit override.
- One request cannot send twice internally and never retries.
- Transport failures return `success=false` with enough context to diagnose.
- No observation batch is emitted for a transmit.

### Django and MCP contracts

- Explicit target ID resolves the requested full target.
- Unknown target ID returns 404 and does not run a plugin.
- Explicit execution does not alter current target.
- Explicit execution **with no current target set at all** runs the plugin and
  leaves current target unset, rather than auto-selecting the first vehicle.
- Omitted target ID retains legacy current-target behavior, auto-select
  included.
- MCP forwards optional target ID without adding a tool.
- Existing plugin execution and interaction lifecycle tests stay green.

### Flutter unit tests

- Both target storage locations index under the correct bus.
- Canonical frame identity includes extended flag.
- Search matches names, decimal IDs, and hex IDs.
- Unsupported/conflicted rows carry reasons.
- Multiplexer changes select the right signal branch.
- Wide numeric text remains text in the outgoing map.
- Any edited field invalidates a prior preview digest.
- Plugin service posts nested request plus explicit target ID.
- Malformed preview responses fail visibly.

### Flutter widget tests

- No selected target blocks opening with a useful message.
- Full-target loading, error, retry, and deleted-target states.
- Bus then frame selection drives signal rows.
- Choice, integer, scaled decimal, signed, and wide fields render correctly.
- Required and backend field errors appear at the correct row.
- Long frame lists are searchable and long signal lists scroll.
- Preview displays exact returned bytes and flags.
- Transmit is disabled before preview and after any edit.
- The channel selector lists scanned CAN devices and sends the interface name,
  not the device ID; an empty scan explains itself rather than showing an empty
  dropdown.
- Confirmation names target, channel, frame, and payload.
- Draft acknowledgement is independent and explicit.
- Double-click cannot submit two sends.
- Closing during an HTTP call causes no post-dispose update.
- Plugins page and Control Panel launch the same shared composer.
- Existing ordinary plugin forms remain unchanged.

Use `MockClient` and `pumpApp()` according to the Flutter testing standard. No
widget test reaches Django or SocketCAN.

### Optional manual integration

After all gates pass, a human-approved diagnostic may:

1. configure a disposable `vcan` interface outside the plugin;
2. preview a known target frame;
3. start an independent `candump` observer;
4. transmit once;
5. verify ID, flags, DLC, and bytes;
6. tear down the disposable interface outside the plugin.

This check is tagged/manual and never part of the deterministic commit gate.
Physical vehicle transmission is not required to complete implementation.

### Required gates

From the root repository:

```bash
tools/testing/test-python-full.sh
```

From `ui/`:

```bash
tools/testing/test-flutter-full.sh
```

Report passed, failed, skipped, warnings, and analyzer issue counts. Do not
weaken unrelated tests or use `--no-verify` to land the feature.

## Safety and security requirements

- Preview is the default and has no I/O side effect.
- Transmit requires a digest from the exact request and target definition.
- Flutter requires a second danger confirmation.
- The plugin sends exactly once and never retries.
- Draft/incomplete targets need an explicit override.
- Target and physical channel are shown together at preview and confirmation.
- Interface setup, bitrate changes, and `sudo` are forbidden inside the client
  and plugin.
- Do not infer that local send success means an ECU received or accepted data.
- Do not expose arbitrary raw payload transmission through this plugin. **Review
  2026-08-24:** this constrains the plugin, not the product. The existing raw
  CAN send screen over `drv_socketcan` remains reachable and unconfirmed, so
  nothing here should be described to an operator as making raw transmission
  impossible.
- Do not add a new unauthenticated mutation endpoint or MCP tool.
- Keep MCP bound to loopback/protected as required by `AGENTS.md`; the existing
  `execute_plugin` exception remains the only MCP execution mutation used.
- Backend validation is authoritative; Flutter validation is convenience only.
- Signal values and payloads must not appear in exception tracebacks or request
  dumps beyond the intentional successful-transmit audit record.

Authentication, authorization, rate limiting, and a general hardware safety
gate remain platform-wide prerequisites. This feature must not pretend that a
preview digest supplies any of those controls.

## Compatibility and migration

- Existing plugins and parameter metadata remain valid.
- `target_can_frame` is additive; unknown clients can pass its value as JSON
  text.
- `target_id` on execute-plugin is optional for backward compatibility.
- Existing targets without newly preserved optional signal fields continue to
  load and encode supported integer/scaled signals.
- No database migration is expected for CAN definitions because target
  topology remains JSON. If exact-target lookup adds no column, Django/SQLAlchemy
  schema is unchanged.
- The existing SocketCAN device driver keeps discovery/streaming ownership and
  need not be rewritten in v1.
- The current target selection UI remains; explicit execution target merely
  removes a race for callers that can supply one.
- No Flutter route change is required.

## Performance constraints

- Do not fetch full target payloads while listing plugins or targets.
- Fetch one full selected target only when the composer opens.
- Build the Dart CAN index once per fetched target.
- Search/filter frame view models, not raw nested JSON on every keystroke.
- Render frame and signal lists lazily.
- Cache reconstructed cantools definitions only within one plugin execution or
  by an immutable target-definition digest; never cache against mutable current
  target identity alone.
- Preview and one-shot transmit should remain synchronous and bounded by the
  configured send timeout.

## Error model

User-facing failures must distinguish:

- target deleted or selection changed;
- CAN bus/frame no longer present;
- conflicting or unsupported definition;
- invalid/missing signal value;
- preview stale;
- draft-target override required;
- SocketCAN interface missing/down/not permitted;
- send timeout;
- local send failure.

Do not collapse these into `CAN send failed`. Messages should identify the
logical bus/frame and physical channel without dumping the full target.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Wrong target because current selection changed | Explicit `target_id`, exact lookup, digest covers target. |
| Wrong same-ID frame on another bus | Bus-scoped identity and conflict rejection. |
| Dart numeric precision loss | Keep edited values as strings; normalize in Python. |
| Incorrect Motorola/multiplexed packing | Reconstruct and use strict cantools encoding. |
| UI and backend catalogue drift | Shared Dart index for UI views; backend re-resolves authoritatively. |
| Stale preview | Invalidate on every edit and verify digest server-side. |
| Accidental repeated injection | One frame per request, disabled in-flight button, no retry/count. |
| Incomplete ARXML target | Draft warning plus explicit backend override. |
| Hidden checksum/counter semantics | No automatic algorithm; require explicit values or reject unsupported. |
| Existing plugin UI regression | Shared renderer preserves ordinary metadata path with characterization tests. |
| Driver/client duplication | Keep client one-shot only; driver retains discovery/lifecycle/streaming and supplies the channel list. Fuzzer CAN wrappers stay untouched in v1. Reuse can follow when behavior matches. |
| Stored CAN definition loses fields on load | Widen facet models and allow extras before the encoder is written; assert resolution through a round-tripped facet. |
| Huge target freezes UI | Full fetch on demand, one index, search, lazy lists. |
| Send success overstated | Wording says local SocketCAN accepted frame only. |

## Acceptance criteria

The plan is complete when all of the following are true:

- The official plugin is discovered through its package entry point.
- A caller can preview a bus-owned ARXML frame and a component-owned DBC frame.
- The plugin strictly encodes physical signal values using target definitions.
- Every codec fixture round-trips through encode and decode without loss.
- Standard, extended, and CAN-FD flags come from the target and reach
  `python-can` correctly.
- No SocketCAN object is opened during preview.
- Transmission is impossible without an exact-target preview digest.
- One transmit request sends exactly one frame and shuts the bus down.
- Draft targets are blocked unless explicitly acknowledged.
- Flutter offers searchable bus/frame selection and typed signal inputs.
- Flutter displays backend-generated payload bytes before confirmation.
- Any edit after preview disables transmission until a new preview succeeds.
- Plugins page and Control Panel share one composer implementation.
- Direct API/MCP object input and CLI JSON-text input use the same schema.
- Existing plugins, generic forms, targets, and current-target callers remain
  compatible.
- Root and Flutter full gates pass.
- No deterministic test touches a real interface or physical vehicle.
- An operator guide documents preview, confirmation, SocketCAN prerequisites,
  direct JSON usage, and limitations.

## Explicit non-goals

- Periodic or cyclic transmission
- Flooding, fuzzing, replay, or batch schedules
- Arbitrary raw `data_hex` send
- Receiving, sniffing, or waiting for an ECU response. `decode_frame` is in
  scope; anything that reads a bus is not.
- Recording observations from CAN traffic, and the sniffer that would produce
  them
- Decoding stored capture files
- ISO-TP segmentation or UDS-over-CAN
- Automatic CRC/checksum/alive-counter/SecOC generation
- AUTOSAR container-frame composition
- Configuring interfaces, bitrate, CAN-FD timing, or link state
- Proving that an ECU received or acted on a frame
- General Django authentication or authorization
- A new MCP mutation/tool
- Replacing the existing SocketCAN streaming device driver
- Adding a second SocketCAN device driver, or changing the existing one's
  commands, lifecycle, or raw CAN send screen
- Consolidating the fuzzer's separate `python-can` wrappers
- Editing target definitions from the composer

## Completion bookkeeping

While implementing, update this file with deviations and the reason for each.
Do not silently change the request schema or safety flow.

When every acceptance criterion is met:

1. add final commit IDs and test counts;
2. record any deferred limitations;
3. move this plan from `docs/exec-plans/active/` to
   `docs/exec-plans/completed/` in the root repository.

---

## Completion record

Implemented 2026-08-25 on branch `feat/can-composer-and-capture` (root) and the
same branch name in `ui/`. All acceptance criteria are met.

### Commits

| Repo | Commit | Covers |
|---|---|---|
| root | `06b505a` | C1–C3: facet widening, `VAL_` parsing, catalogue, codec, SocketCAN client, composer plugin |
| root | `9218cf7` | C4: exact-target execution in Django and MCP |
| root | `dc17d8a` | K1–K3: bounded receiver, aggregator, capture plugin (capture plan) |
| `ui/` | `6d28ab4` | C5–C6 and K4: shared parameter flow, composer UI, capture table |

### Test counts

- Root gate `tools/testing/test-python-full.sh`: **1025 passed**, 0 failed,
  0 skipped, 42 warnings, ruff clean. Baseline before this work was 869.
- Flutter gate `tools/testing/test-flutter-full.sh`: **448 passed**, 0 failed,
  analyzer 0 issues, `dart format` clean. Baseline was 395.

The 42 Python warnings are pre-existing and unrelated (SQLAlchemy 2.0
`declarative_base` deprecation, `python_multipart`, two internal deprecations).

### Deviations from the plan, and why

1. **Phase 2's order was inverted relative to phase 1.** The plan puts fixtures
   first, but the "component-owned frame carrying choices" fixture cannot be
   written against a stored model that drops `choices` on load. C2a (facet
   widening + `VAL_`) was done first, then the fixtures, then the codec.
2. **`definitions.py` was added** beside `catalog.py` and `codec.py`. The plan
   lists three modules; the frozen types are the vocabulary all three share and
   putting them in `catalog.py` would have made it the largest file in the
   package. Same package, no new dependency.
3. **A name mismatch between two definitions of one identity is treated as a
   conflict.** The plan's step 7 lists DLC, layout, scaling, multiplexing and
   FD state but not the name. Leaving the name out makes it undefined which of
   two differently-named rows survives, and the plan's own instruction is to
   fail rather than choose silently. Documented here rather than changed
   quietly.
4. **`canbus/errorframes.py` duplicates nine constants** from
   `iotsploit_drivers.socketcan.can_errors` (capture plan's requirement).
   `iotsploit-drivers` depends on `iotsploit-core` alone, so importing it from
   `iotsploit-protocols` would add a package edge neither plan sanctions. Same
   precedent as `canonical_frame_id`. Worth consolidating if drivers ever
   depends on protocols.
5. **`get_all_targets()` was refactored** to share a row-to-dict helper with
   the new `get_target()`. Not in the plan, but leaving two copies of the
   folded-target shape is how they drift.
6. **The explorer was not refactored to delegate its CAN enumeration, and this
   is an unmet item rather than a judgement call.** Phase 5 asks for the
   existing indexing in `TargetModel` to be extracted or delegated "so the
   explorer and composer share the same bus-owned/component-owned enumeration
   rules". `TargetCanIndex` was added, but
   `lib/screens/targets/explorer/explorer_model.dart` still has its own
   `framesOf` / `busFrames`. The two read the same two locations and agree
   today; nothing enforces that they keep agreeing, which is exactly the drift
   the plan wanted closed. The shapes differ enough (typed views grouped by bus
   versus raw maps for a tree) that folding them together is a real refactor of
   the explorer's tree building, and doing it under this change would have put
   an untested rewrite of a working screen inside a CAN feature. Recorded here
   as the plan's bookkeeping section instructs.

### Two bugs the tests caught while being written

- The SocketCAN channel pattern used `$`, which in Python matches *before* a
  trailing newline — `"can0\n"` validated as a usable interface name.
- `python-can`'s `check=True` raises from the `Message` constructor rather than
  from `send()`, so an unrepresentable frame escaped as a bare `ValueError`
  past every caller's `except` clause.

### Hardware validation

Performed against a PCAN-USB FD adapter on the Pi at 10.8.0.10, outside the
commit gate as the plan requires.

- **Receive, against a live 500 kbit FD bus** (~4.5M frames already received):
  2355 frames in 5.01s across 25 identities, measured periods landing exactly
  on 10/20/50/100 ms, FD payloads of 16 and 24 bytes handled, zero error frames
  in the window, and — the point of the exercise — **no phantom `0x004` row**.
- **Codec, against real captured payloads**: a 16-byte FD frame carrying a
  64-bit signal and a labelled choice decoded and re-encoded identically, on
  the Pi's Python 3.13.5 and cantools 42.0.3.
- **Transmit, on a disposable `vcan0`** created and destroyed outside
  IoTSploit. An independent `candump` witnessed both frames byte-for-byte:
  `123 [8] A9 01 0E 00 00 00 00 00` and
  `01ABCDEF [16] FF FF FF FF FF FF FF FF 00…` — confirming the standard frame
  stayed standard (python-can defaults `is_extended_id` to `True`) and that
  2^64-1 survived as text.
- The live bus was **not** transmitted onto. `can0` TX remained 0 packets
  throughout, verified after teardown.

### Deferred

- No `operation: "decode"` on the composer contract. `decode_frame` exists and
  is used for the preview read-back and by the capture, but nothing exposes
  "give me bytes, get signals" to an API caller. Cheap to add now that the
  codec exists; deliberately not decided here.
- Decoding stored capture files remains unbuilt, as both plans intend.
- `iotsploit-protocols/pyproject.toml` carries its own
  `[tool.pytest.ini_options]` without the marker registry, so running that
  package's tests by path disables `--strict-markers`. Pre-existing, affects
  several packages, not touched here.
