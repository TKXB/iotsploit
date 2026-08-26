# Target-Aware CAN Live Capture and Decode Plan

## Status

Drafted 2026-08-24, accepted and **completed 2026-08-25**. The composer
plan's phase 2 exited first, as this plan requires. See the completion record
at the end of this file.

This is the receiving half of CAN work. The sending half is
`can_frame_composer_plugin_plan.md`, which is accepted and which this plan
depends on: the target catalogue, the reconstructed `cantools` definitions, and
`decode_frame` are built there and are consumed unchanged here. **Do not start
this plan before that one's phase 2 exits**, or the catalogue and codec get
written twice against the same definitions.

Both plans touch the root repository and the nested `ui/` Flutter repository,
which are committed, reviewed, and merged independently.

## Objective

Let an operator watch a CAN bus through a configured SocketCAN interface and
see decoded signal values from the active target's own definitions, instead of
raw hex. When the capture ends, record what was seen as durable observations,
so the gap between what the ARXML/DBC claims and what the bus actually carries
becomes answerable.

The capture is **bounded and read-only**. It has a duration or frame budget, it
ends by itself, and it transmits nothing.

## User-visible result

```text
Target:  Bench Vehicle          Bus: Powertrain CAN          Channel: can0
Capturing 30s · 4210 frames · 47 ids · 3 undefined      [Stop]

ID     Name             Count  Period    Last decoded
0x123  VehicleStatus     2981   10ms     VehicleSpeed 42.5 km/h · IgnitionState On
0x2A1  BrakeStatus        598   50ms     BrakePressure 0.0 bar · AliveCounter 7
0x0C4  —                  312   100ms    (no definition on this bus)
0x3F0  TransmissionData   119   250ms    decode failed: payload 6 bytes, DLC 8
```

Rows update in place. The list is per frame identity, not per frame received: a
scrolling log of every frame on a busy bus is unreadable and would flood the
socket, so the stream carries periodic snapshots of this table.

## Relationship to what already exists

- `SocketCANDriver` already streams **raw** frames and
  `ui/lib/screens/tasks/components/can_screen.dart` already renders them. That
  pairing stays exactly as it is: it is the device-level view, it needs no
  target, and it works when no target is selected. This plan adds the
  target-aware view beside it, and does not modify the driver.
- The observation model is already shaped for this. `Fact` carries
  `protocol`/`subject_kind`/`subject_id`; `canonical_frame_id` in the CAN facet
  exists specifically to be a CAN observation's `subject_id`; the explorer
  already renders `protocol == "can"`, `subject_kind == "message"` rows.
- `tools/seed_can_observations.py` fabricates exactly these facts, and says in
  its own docstring that it exists because no sniffer plugin does. **This plan
  is what retires it.** The real capture must emit the same fact shape the
  seeder does — `observed_property="seen"`, value carrying `name`, `count`,
  `period_ms`, `dlc` — so the explorer and any reconciliation keep working, and
  the seeder becomes a fixture generator rather than a stand-in.
- Long-running plugins are already supported end to end: a `duration` over 5
  routes to the task runner, and the Celery task calls back through
  `run_plugin_in_process`, so the queued path records the same scan lifecycle
  as a synchronous run. A bounded capture therefore gets scans for free.

## Decisions

| # | Decision | Chosen behavior | Reason |
|---|---|---|---|
| 1 | Component | A bounded exploit plugin, not a device driver change | The driver is target-agnostic and privileged; decoding needs target definitions and needs none of its lifecycle. |
| 2 | Transport | The capture opens its own receiving SocketCAN socket | SocketCAN permits several sockets on one interface, so this neither disturbs nor depends on the driver's stream. |
| 3 | Boundedness | Every capture has a duration and a frame budget, whichever ends first | An unbounded loop in a worker is a leak, and an observation scope needs a run that ends. |
| 4 | Decoding | `decode_frame` from `iotsploit_protocols.canbus`, unchanged | One codec, proven by the composer's round-trip tests. |
| 5 | Streaming shape | Periodic aggregated snapshots, not one message per frame | A 500 kbit bus carries thousands of frames a second; per-frame messages would flood the socket and the UI. |
| 6 | Observations | One batch per captured bus, `is_complete=False` in v1 | A capture window is a sample, not a census. See *Completeness*. |
| 7 | Undefined frames | Recorded as seen, marked as having no definition | A frame nobody documented is the finding, not noise to discard. |
| 8 | Decode failures | Counted and reported per frame identity, never logged per frame | Per-frame logging of a malformed 100 Hz frame writes 6000 lines a minute. |
| 8a | Error frames | Classified as bus health before identity is read, never as traffic | Their `arbitration_id` is an error class, not an address; counting them as frames invents an ECU that does not exist. |
| 9 | Bus effects | The plugin never transmits, and states plainly that a non-listen-only controller still ACKs | Silence about hardware-level ACK would be a false safety claim. See *Safety*. |
| 10 | Target selection | Explicit `target_id`, as the composer plan establishes | The definitions used to decode must be the ones the operator was looking at. |
| 11 | Raw view | The existing raw CAN screen is untouched | It is the fallback when no target, no definitions, or no decode is wanted. |

## Architecture

```text
Flutter capture view
  -> structured request + explicit target_id (bus, channel, duration, budget)
  -> Django execute-plugin, routed async by duration
  -> CAN Live Capture plugin
       -> target catalogue resolver          (from composer plan)
       -> definitions indexed by identity    (built once, before the loop)
       -> receiving SocketCAN client
       -> per-identity aggregator
            -> periodic StreamData snapshots -> WebSocket -> live table
            -> final tallies
       -> ObservationBatch                   -> scan lifecycle -> explorer
```

Dependency direction is the composer plan's, unchanged:

```text
iotsploit-exploits -> iotsploit-protocols -> iotsploit-core
```

The receiving client is a sibling of the composer's `SocketCanClient` in the
same module, not a second transport module.

## Plugin contract

One packaged entry point:

```toml
can_live_capture = "iotsploit_exploits.canbus.live_capture:CanLiveCapturePlugin"
```

Request, alongside the execution boundary's `target_id`:

```json
{
  "schema_version": 1,
  "bus_id": "bus_can_powertrain",
  "transport": {"interface": "socketcan", "channel": "can0"},
  "duration_s": 30,
  "max_frames": 200000,
  "snapshot_interval_ms": 200,
  "decode": true
}
```

`duration_s` over 5 routes the run to the task runner, which is the intended
path; the plugin must also behave correctly when run synchronously with a short
duration, because that is how tests will drive it.

Result data:

```json
{
  "bus": {"bus_id": "bus_can_powertrain", "name": "Powertrain CAN"},
  "transport": {"channel": "can0"},
  "window": {"started_at": "...", "ended_at": "...", "duration_s": 30.0},
  "totals": {"frames": 4210, "identities": 47, "undefined": 3, "undecodable": 1},
  "frames": [
    {
      "frame_id": 291,
      "frame_id_hex": "0x123",
      "is_extended": false,
      "name": "VehicleStatus",
      "known": true,
      "count": 2981,
      "first_seen_at": "...",
      "last_seen_at": "...",
      "period_ms": 10,
      "dlc": 8,
      "last_data_hex": "0300A90100000000",
      "last_signals": {"VehicleSpeed": 42.5, "IgnitionState": "On"},
      "decode_errors": 0
    }
  ]
}
```

`period_ms` is derived from observed inter-arrival times, not copied from the
definition's declared cycle time. Reporting the declared value as if it were
measured is how a capture stops being evidence.

## Live streaming

- Broadcast `StreamData` with `StreamType.CAN` on a channel owned by this run,
  distinct from the device driver's channel (which is a device ID). Colliding
  with the driver's channel would interleave decoded snapshots with raw frames
  in one socket.
- One message per `snapshot_interval_ms`, carrying only rows that changed since
  the previous snapshot, plus running totals.
- The snapshot rate is fixed by the request, never by the frame rate.
- The receive loop must not block on the broadcast: a slow or absent consumer
  drops snapshots and keeps capturing, rather than stalling the socket and
  losing frames.

## Aggregation and decode

Before the loop:

1. Resolve the bus and build the identity-to-definition index once, using the
   composer plan's catalogue. Conflicted definitions are marked and their frames
   are counted but never decoded.
2. Reconstruct each `cantools` message once. Rebuilding per frame at thousands
   of frames per second is the difference between a working capture and a
   dropped one.

### Error frames are not traffic

A SocketCAN socket delivers **error frames** alongside data frames, and
`python-can` enables them by default (`CAN_RAW_ERR_FILTER`, unless
`ignore_rx_error_frames=True`). They are not messages: the ERR flag lives in the
CAN ID, and once `python-can` masks it off, what remains in `arbitration_id` is
an *error class*, not an address. `CAN_ERR_CRTL` presents as arbitration ID
`0x004` with the controller status in `data[1]`.

Anything that keys on `(arbitration_id, is_extended)` without checking
`is_error_frame` therefore invents a frame `0x004` that no ECU ever sent, counts
bus faults as traffic, and — because this plan writes observations — would
record that phantom frame as a documented-vs-observed finding against the
target. `SocketCANDriver` had exactly this defect, which is why its stream
showed a bursty `0x004` on a bus whose `candump` was clean: plain `candump` does
not enable error frames, so the two disagreed. The driver now classifies before
it reads identity (`iotsploit_drivers.socketcan.can_errors`); this capture must
do the same rather than assume everything reaching it is traffic.

The capture must therefore:

- test `is_error_frame` **before** identity, and never let an error frame reach
  the aggregator, the frame table, or an observation;
- decode the error class and, for `CAN_ERR_CRTL`, the `data[1]` status, into a
  separate bus-health tally: rx/tx warning, rx/tx passive, bus-off, overflow,
  ACK, protocol violations;
- surface that tally in the live view and the result, because on real hardware
  it is the most valuable signal there is. A bus that is error-passive is
  telling you the bitrate is wrong, the FD configuration is wrong, or the wiring
  is wrong — which is the actual explanation for a capture that "sees nothing";
- treat `is_remote_frame` as its own category too, not as a zero-length data
  frame.

A capture whose error counts are high and whose data frame count is low must say
so in its summary rather than reporting an empty bus.

Per received frame:

1. Key by `(arbitration_id, is_extended)`, the same identity the composer uses.
2. Update count, first/last seen, inter-arrival statistics, and last payload.
3. Decode when a definition exists and `decode` is true; on failure, increment
   that identity's error count and keep the first reason. Never raise, never log
   per frame.
4. A frame with no definition is counted with `known: false`. Cap the number of
   distinct unknown identities retained; on overflow, stop adding new ones and
   flag the result, rather than growing without bound on a fuzzed or noisy bus.

## Observations

One `ObservationBatch` per captured bus. Scope key names the bus, so two buses
captured separately never overwrite each other's history.

Facts mirror the seeder's existing shape:

- `protocol="can"`, `subject_kind="message"`,
  `subject_id=canonical_frame_id(frame_id, is_extended)`,
  `observed_property="seen"`;
- value carries `name`, `count`, `period_ms`, `dlc`, and additionally `known`
  and `decode_errors`, which the simulation had no way to produce.

### Completeness

`is_complete=False` in v1, deliberately. A complete batch is how this model says
"this is the whole population now", and it clears prior state. A thirty-second
capture cannot say that: a frame on a sixty-second cycle is absent from the
window without being absent from the vehicle, and marking the batch complete
would record it as having disappeared.

A later version may set `is_complete=True` when the window provably exceeds a
multiple of the slowest declared cycle time on that bus, but that rule needs its
own justification and tests. Until then, captures accumulate as history and
never retract earlier findings.

## Safety

- The plugin transmits nothing. There is no send path in it, not even a
  disabled one.
- **A CAN controller in normal mode acknowledges frames it receives at the
  hardware level.** Attaching an interface to a live vehicle bus is therefore
  not electrically inert, whatever the software does. Listen-only mode is host
  link configuration (`ip link ... listen-only on`), which this plugin must not
  set, exactly as the composer must not set bitrate or link state. The operator
  guide must say this plainly, and the UI must show whether the selected
  interface is a virtual `vcan` before a capture starts.
- `RequiresRoot` stays false. Receiving on an interface that is already up is
  unprivileged, and the root path does not carry a full target snapshot.
- Captured payloads are target data. They go into the result and the observation
  value; they must not be written to logs at info level or into tracebacks.
- The capture must stop when its budget is reached even if the consumer has gone
  away, and must close its socket on every exit path including cancellation.

## Files expected to change

### Root repository

| File | Change |
|---|---|
| `iotsploit-protocols/src/iotsploit_protocols/canbus/socketcan.py` | Add a bounded receiving client beside the one-shot sender. |
| `iotsploit-protocols/tests/test_socketcan_client.py` | Receive lifecycle, budget, and shutdown with a fake bus. |
| `iotsploit-exploits/src/iotsploit_exploits/canbus/live_capture.py` | Aggregation, decode, snapshots, observation batches. |
| `iotsploit-exploits/tests/test_can_live_capture.py` | Aggregation and observation contract against a scripted frame source. |
| `iotsploit-exploits/pyproject.toml` | Register the entry point. |
| `tools/seed_can_observations.py` | Reduce to a fixture generator, or retire, once real captures produce the same shape. |
| `docs/product-specs/can-live-capture.md` | Operator guide, ACK warning, listen-only prerequisites. |

### Flutter repository

| File | Change |
|---|---|
| `lib/models/can_capture.dart` | Row view models and snapshot merge logic. |
| `lib/widgets/plugins/can_capture_view.dart` | Live table, totals, stop control. |
| `lib/screens/tasks/components/can_screen.dart` | Unchanged; note in code why the raw view stays. |
| `test/unit/can_capture_model_test.dart` | Snapshot merging, ordering, unknown/error rows. |
| `test/widget/can_capture_view_test.dart` | Live updates, stop, end-of-run summary. |

## Testing requirements

Deterministic tests drive a scripted frame source. No test opens `can0`,
`vcan0`, or a socket.

- A frame with a definition decodes to named signals; the same bytes through
  the composer's `decode_frame` give identical values.
- A frame with no definition is counted as `known: false` and never decoded.
- An error frame never appears in the frame table or in any fact, and lands in
  the bus-health tally instead; `CAN_ERR_CRTL` with `data[1] = 0x04` is reported
  as rx-warning and `0x10` as rx-passive.
- A capture of nothing but error frames reports a faulted bus, not an empty one.
- A remote frame is counted as a remote frame, not as a zero-length data frame.
- A malformed payload increments `decode_errors`, keeps the first reason, and
  does not stop the capture.
- Period is measured from arrival times and differs from a deliberately wrong
  declared cycle time in the fixture.
- The duration budget and the frame budget each end the capture on their own.
- Distinct-unknown-identity overflow flags the result instead of growing.
- Snapshots arrive at the configured interval regardless of frame rate, and
  carry only changed rows.
- A consumer that never reads does not stall or fail the capture.
- The socket is closed after success, after budget exhaustion, and after error.
- The observation batch is `is_complete=False`, one scope per bus, with facts in
  the seeder's shape.
- A capture that raises still fails its scan rather than leaving it running.
- Conflicted definitions are counted but not decoded.

Both full gates apply, as in the composer plan: `tools/testing/test-python-full.sh`
from the root and `tools/testing/test-flutter-full.sh` from `ui/`.

An optional manual `vcan0` check may follow the deterministic suite: replay a
known log with `canplayer`, capture it, and compare decoded values against the
definitions. Never part of the commit gate.

## Implementation phases

1. **Receiving client.** Bounded receive with injected bus factory, budgets,
   and guaranteed shutdown. Exit: lifecycle asserted with fakes only.
2. **Aggregator and decode.** Pure per-identity aggregation over a scripted
   frame source, with no socket and no stream. Exit: every aggregation and
   decode-failure test passes without I/O.
3. **Plugin, streaming, observations.** Wire the two together, add snapshots and
   the observation batch. Exit: scan lifecycle recorded on success and failure;
   snapshot cadence independent of frame rate.
4. **Flutter capture view.** Live table, totals, stop, summary. Exit: widget
   tests cover the full run without a backend.
5. **Documentation and validation.** Operator guide including the ACK warning
   and listen-only prerequisites; both gates; optional `vcan0` replay.

## Acceptance criteria

- A capture against a target's bus produces decoded signal values from that
  target's own definitions.
- Undefined and undecodable frames are visible and counted, not silently
  dropped.
- Error frames are reported as bus health and never as traffic or observations.
- Measured periods come from arrival times.
- A capture ends on its own budget and closes its socket on every path.
- Observations appear in the explorer in the same shape the seeder produced,
  and no capture retracts an earlier finding.
- The raw CAN screen and the SocketCAN driver are unchanged and still work with
  no target selected.
- Nothing in the capture path can transmit.
- The operator guide states that a normal-mode controller ACKs on the bus.
- Both full gates pass; no deterministic test touches a real interface.

## Explicit non-goals

- Transmitting anything, including replies, ACK suppression, or error frames
- Cyclic or triggered send (that is the composer plan, and it stays one-shot)
- ISO-TP reassembly or UDS-over-CAN decoding
- Decoding stored capture files (a third feature, reusing the same codec)
- Writing captured traffic to a log file format
- Diffing a capture against the definition catalogue, or proposing target edits
  from what was seen
- Changing `SocketCANDriver`, its commands, or the raw CAN screen
- Configuring interfaces, bitrate, or listen-only mode
- Inferring that an unseen frame is absent from the vehicle

## Completion bookkeeping

While implementing, update this file with deviations and the reason for each.
When every acceptance criterion is met, add final commit IDs and test counts,
record deferred limitations, and move this plan to `docs/exec-plans/completed/`.

---

## Completion record

Implemented 2026-08-25 alongside the composer plan, on branch
`feat/can-composer-and-capture` in both repositories. The gating condition was
honoured: the composer plan's phase 2 exited (commit `06b505a`) before any of
this was written, so the catalogue, the reconstructed `cantools` definitions,
and `decode_frame` are consumed here unchanged rather than written twice.

### Commits

- root `dc17d8a` — bounded receiving client, aggregator, capture plugin,
  streaming snapshots, observation batches.
- `ui/` `6d28ab4` — capture table, snapshot merge model, Component Showcase
  entries.

### Test counts

Both gates green: **1025 Python** and **448 Flutter**, 0 failures. 34 of the
Python tests are this plan's, driving a scripted frame source; no test opens a
socket.

### Deviations

1. **SocketCAN error constants are duplicated** rather than imported from
   `iotsploit_drivers.socketcan.can_errors`. Drivers depends on core alone, and
   importing it from protocols would add a package edge neither plan sanctions.
   The two are not redundant in output — the driver formats a `candump -e`
   style description for a live stream, this produces a per-class tally — but
   they do share nine integers from `linux/can/error.h`.
2. **The aggregator lives in the plugin module**, as the plan's file table
   says, but is a standalone class with no plugin dependency so it can be
   driven directly by tests.
3. **The snapshot sink is injected.** The plan describes broadcasting
   `StreamData` directly; making the sink a parameter is what lets every
   snapshot-cadence and hostile-consumer test run without a stream manager.
4. **`tools/seed_can_observations.py` was left in place** rather than reduced.
   Real captures now produce the same fact shape, so it is a fixture generator
   as intended, but nothing was deleted — retiring it is a separate call.

### Hardware validation

Read-only capture against a live 500 kbit CAN FD bus on the Pi at 10.8.0.10:
2355 frames in 5.01s, 25 identities, measured periods landing exactly on
10/20/50/100 ms, FD payloads of 16 and 24 bytes, and no error frame ever
reaching the frame table. Nothing was transmitted; `can0` TX stayed at 0
packets.

The bus-off / error-passive path was exercised deterministically rather than on
hardware — the adapter's cumulative counters showed 10,813 historical
error-passive events, but the capture window itself was clean.

### Deferred

- `is_complete=True` for a window that provably exceeds a multiple of the
  slowest declared cycle time. Needs its own justification and tests.
- Diffing a capture against the catalogue, and decoding stored capture files.
  Both remain non-goals.
