# Target-Aware CAN Bus Monitor Plan

## Status

Drafted 2026-08-25 on branch `feat/can-composer-and-capture`, after both CAN
plans completed. Accepted, implemented, and validated 2026-08-25 at the
user's request.

This is the third piece of CAN work. The first two —
`can_frame_composer_plugin_plan.md` (sending) and `can_live_capture_plan.md`
(evidence) — are complete, and this plan consumes what they built without
modifying either contract. It adds no protocol code and no decoder.

Both repositories are touched: the root repository and the nested `ui/`
Flutter repository, which are committed, reviewed, and merged independently.

## Objective

Let an operator open the CAN Bus Monitor, pick a target and the bus its adapter
is wired to, and watch decoded signal values scroll by **as frames arrive** —
instead of raw hex, and instead of waiting for a bounded capture to finish and
print everything at once.

The monitor is for *watching*. The capture plugin remains the tool for
*evidence*: bounded windows, recorded observations, a defensible sample. This
plan does not blur that line, and says where each one belongs.

## What this supersedes

`can_live_capture_plan.md` decided the opposite of this plan, twice, and did so
deliberately:

> Decision 11 | Raw view | The existing raw CAN screen is untouched | It is the
> fallback when no target, no definitions, or no decode is wanted.

and, under *Explicit non-goals*:

> Changing `SocketCANDriver`, its commands, or the raw CAN screen

That call was right for that plan: a capture is a bounded evidence run and had
no business reaching into a device screen. It is wrong as a permanent rule, for
a reason that only became visible once both halves shipped — **the decoded live
table was built at both ends and never connected in the middle**, so the only
way to see decoded traffic today is to wait for a capture to end and read its
result. The monitor is where an operator already goes to watch a bus.

This plan therefore reopens decision 11. It still does not change
`SocketCANDriver`: the driver's raw stream stays exactly as it is, and stays
the no-target fallback. What changes is that the monitor screen gains a second,
optional source.

## User-visible result

```text
Target: Bench Vehicle    Bus: BKBCANFD ▾  [Identify bus]    Interface: can0
Decoding · 4210 frames · 47 ids · 3 undocumented                      [Stop]

ID     Name             Count  Period   Data              Decoded
0x123  VehicleStatus     2981   10ms    4A0100003201F400  VehicleSpeed 42.5 km/h
0x2A1  BrakeStatus        598   50ms    0000070000000000  BrakePressure 0.0 bar
0x0C4  —                  312  100ms    88AA00FF          no definition on this bus
0x3F0  TransmissionData   119  250ms    01FF02AB55        decode failed: payload 6 bytes, DLC 8
```

With no target selected the screen is exactly what it is today: raw hex, no
names, no target, no decode. Decoding is strictly additive and always optional.

The raw payload column stays visible **next to** the decoded column, in every
mode. An operator must always be able to see the bytes the interpretation came
from; a decoded value with no bytes beside it is an assertion nobody can check.

## Relationship to what already exists

The two halves of this feature exist and were built to fit each other. Nobody
joined them:

| Piece | Where it is | State |
|---|---|---|
| Per-identity rows, cantools decode, measured periods, error-frame separation | `CaptureAggregator`, live_capture.py:140 | Exists, tested |
| Changed-rows snapshot `{rows, totals, bus_health, final}` | `_emit`, live_capture.py:442 | Exists, tested |
| Broadcast to channel `can_capture_<bus_id>` | `_snapshot_sink`, live_capture.py:753 | Exists |
| WebSocket route carrying that channel | `ws/device/stream/<channel>/` | Exists |
| Dart model folding snapshots into a stable table | `CanCaptureViewData.merge()`, ui/lib/models/can_capture.dart:128 | Exists, tested |
| The decoded live table widget | `CanCaptureView` | Exists — wired only to the Component Showcase |
| Which documented bus an interface is wired to | `tools/match_can_bus.py` | Exists — as a standalone CLI script |
| Full target payload for the Dart CAN index | `TargetsService.getTarget()` → `TargetCanIndex.fromTarget()` | Exists, used by the composer |

`CanCaptureRow.fromJson` consumes `FrameRow.as_dict()` field for field. The
contract is already agreed on both sides of a wire nobody connected.

Most of this plan is wiring. The genuinely new work is target/bus selection on
the monitor, a run-until-stopped session shape, and a queue that a long session
cannot starve.

## Decisions

| # | Decision | Chosen behavior | Reason |
|---|---|---|---|
| 1 | Decoder language | **Python**, `cantools` via the existing `CanCodec`. No Dart decoder. | See *Why not Dart*. |
| 2 | Producer | The existing CAN Live Capture plugin, in a run-until-stopped mode | It already aggregates, decodes, measures periods, and separates error frames. A second producer would be a second decoder by another name. |
| 3 | Consumer | The existing `CanCaptureView`, embedded in the monitor screen | Written for this snapshot shape, tested, and currently unreachable. |
| 4 | Raw view | Stays, unchanged, as the no-target mode of the same screen | It is the only view that works with no target, no definitions, or a bus nobody has identified yet. |
| 5 | Driver | `SocketCANDriver` is not modified | Decoding needs target definitions; the driver is target-agnostic and must stay so. SocketCAN permits several sockets on one interface. |
| 6 | Bus choice | Explicit, never inferred, with `match_can_bus` offered as an aid | Picking the wrong bus does not fail — every id resolves and every value is wrong. See *Which bus*. |
| 7 | Session bound | Run-until-stopped, with a hard ceiling and a memory ceiling | A monitor whose session silently ends is broken; a monitor with no ceiling at all is a leak in a worker. |
| 8 | Stop | Cooperative, through `ask.check_cancelled()` in the receive loop | The mechanism exists, is rate-limited, and is documented for exactly this. See *Stopping*. |
| 9 | Observations | A monitor session records **none** | Watching is not evidence. A session of arbitrary length is not a sample anyone can reason about. See *Observations*. |
| 10 | Queue | A monitor session must not run on the `interactive` queue | That queue is concurrency 1. One monitor session would block every prompt in the product for its whole duration. See *Queueing*. |
| 11 | Transmit | The monitor's send panel is untouched and target-unaware | Composing against definitions is the composer's job, with its preview digest and draft-target guard. Decoding is read-only; it must not quietly grow a send path. |

## Why not Dart

Decoding client-side is tempting: `TargetCanIndex` already parses every signal's
layout, the payload is already on screen, and it would cost no backend work.
Three facts rule it out.

**The codec already ruled on it.** `iotsploit_protocols/canbus/codec.py` states
the position in its own docstring:

> Big-endian straddling, signed two's complement across a byte boundary, and
> multiplexed layouts are exactly the places a hand-rolled packer looks right
> and is wrong, which is why none of that arithmetic appears here.

A Dart decoder is that packer's inverse, hand-rolled. An OEM ARXML extract is
precisely where those layouts live. The same docstring also disposes of the
obvious mitigation: a hand-written vector and a mistaken implementation can
agree while both misplace the same bits.

**Dart's integers are 53-bit on the web, and web is a shipping target**
(`flutter build web --release`, ui/README.md:75).
`ui/lib/models/can_frame_composer.dart` already refuses to parse signal values
in Dart for this reason and keeps them as `String` all the way to Python.
Decoding hits the same wall from the other side, with `factor`/`offset` scaling
in `double` on top of it.

**Python is less work here, not more.** The Python decoder runs anyway for the
composer and the capture; choosing it makes this feature wiring. Choosing Dart
means writing a second CAN decoder, testing it, and then keeping two
implementations in agreement forever.

The `TargetCanIndex` mirror keeps its existing job — letting an operator *find*
a bus and a frame without a round trip. It does not gain a decode path.

## Architecture

```text
CAN Bus Monitor screen
  target ▾  bus ▾  interface ▾
      |
      |-- no target ------> ws/device/stream/<device_id>/   (unchanged today)
      |                       SocketCANDriver, raw frames
      |
      `-- target + bus ---> POST /api/execute_plugin/  (CAN Live Capture,
                              full `request`, mode: monitor)
                              |
                              v
                          monitor queue worker
                              CAN Live Capture plugin
                                -> TargetCanCatalog + CanCodec   (unchanged)
                                -> SocketCanReceiver             (unchanged)
                                -> CaptureAggregator             (unchanged)
                                     -> snapshots -> can_capture_<bus_id>
                              |
                              v
                          ws/device/stream/can_capture_<bus_id>/
                              |
                              v
                          CanCaptureViewData.merge() -> CanCaptureView
```

Dependency direction is unchanged:

```text
iotsploit-exploits -> iotsploit-protocols -> iotsploit-core
```

No new package edge. `iotsploit-drivers` is not touched and does not learn
about targets or protocols.

## Which bus is wired to this interface

A vehicle ARXML describes many buses — the ZXD V5 extract describes eleven —
and an adapter is plugged into exactly one. Choosing the wrong one **does not
fail**: every frame id still resolves, every signal still decodes, and every
value is wrong. Silent wrongness is the worst outcome this feature can produce,
so:

- the bus is an explicit choice, never defaulted to the first bus, never
  inferred from a name that happens to look like the interface;
- `tools/match_can_bus.py` becomes reachable from the UI as **Identify bus**:
  listen read-only for a few seconds, score each documented bus by how much of
  the observed traffic it explains, show the table;
- both failure shapes are reported, not just the happy one. Nothing explaining
  the traffic means the wrong ARXML or the wrong interface. A near-tie means
  listen longer, not pick one. On the bench PCAN adapter the separation was
  100% against 64%, and that margin is the signal to look for.

Moving the tool's scoring out of `tools/` and into a place both the CLI script
and the UI can call is part of this plan; duplicating it is not.

## Session shape

### Starting

The monitor builds a full `request` object and executes the plugin. Because a
request is supplied, the plugin asks nothing — `parse_request` handles it today
and the interactive path is skipped (live_capture.py:667).

The request gains one field:

```json
{
  "schema_version": 1,
  "bus_id": "BKBCANFD",
  "transport": { "interface": "socketcan", "channel": "can0", "fd": true },
  "mode": "monitor",
  "duration_s": 3600,
  "max_frames": 20000000,
  "snapshot_interval_ms": 200,
  "decode": true
}
```

`mode` defaults to `capture`, which is exactly today's behavior. Absent, every
existing API, MCP, and CLI-JSON caller is unaffected.

### Bounded, still

`mode: "monitor"` does not mean unbounded. It means the budget is a **ceiling
rather than a plan**:

- a hard duration ceiling (default 1 hour) so a forgotten session in a worker
  ends by itself;
- the frame budget stays, raised;
- `MAX_UNKNOWN_IDENTITIES` (2048, live_capture.py:79) already stops an
  unbounded row dict on a fuzzed or misconfigured bus, and already reports that
  it stopped. A monitor session must surface `unknown_overflowed` in the live
  view, not only in the final result — on a long session it is the difference
  between "quiet" and "no longer counting".

### Stopping

`service.cancel_execution()` (interaction/service.py:101) marks the row
cancelled and closes pending prompts — but a capture loop that is not waiting
on a prompt never notices. The receive loop must therefore check, and the
mechanism for that already exists and is documented for it:

> `check_cancelled` — Rate limited: plugins are encouraged to call this inside
> tight loops. (interaction/adapter.py:58)

So `capture_frames` gains an optional cancellation callback, called where it
already checks the snapshot clock — no new timer, no new thread. When it
raises, the existing `with SocketCanReceiver(...)` unwinds and closes the
socket on the way out, which is already tested on every exit path.

`SocketCanReceiver.stop()` (socketcan.py:275) stays what it is: the in-process
flag. The cancellation callback is what reaches it from another process.

### Queueing

`Interactive: True` routes every execution of this plugin to the `interactive`
queue (plugin_views.py:357), which runs at **concurrency 1** by deliberate
design — it is what lets the Control Panel show a single unambiguous question.

An hour-long monitor session on that queue blocks every prompt in the product
for an hour. That is not acceptable and it is not a detail to discover during
testing.

The fix is a separate queue for runs that stream rather than ask. A monitor
session still wants everything else the interactive path gives it — a durable
execution row, a bound interaction port so Stop works, the log transcript — so
the answer is not "route it to the general queue" (which binds no port at all,
plugin_tasks.py:57). It is the same task on a different queue, chosen by the
request rather than by the plugin's metadata.

### Snapshot transport

Snapshots go to `can_capture_<bus_id>` over `ws/device/stream/`, as they do
today, and the monitor subscribes to that channel. The channel name is
derivable from the bus the operator picked, so nothing has to be discovered.

The alternative — emitting snapshots as execution events on
`/ws/execution/<id>/`, giving the client one socket instead of two — is
attractive and is left open deliberately. It couples the snapshot rate to the
execution event path, whose own docstring says events are notifications rather
than a replayable log, and a dropped snapshot loses a row's latest state until
that row changes again. Decide it in phase 3 with both consumers in front of
you; do not decide it in the abstract.

## Observations

A monitor session records **no observations**, and this is a decision rather
than an omission.

`observation_scopes` must return `[]` for `mode: "monitor"`, or the manager
will fail a scope the run produced no batch for. The capture plugin's existing
`is_complete=False` reasoning is about a *bounded window* being a sample of a
population. A session an operator started at some point and stopped at another
is not a sample anyone can reason about later, and writing it as one would put
the least defensible evidence in the product into the same table as the most.

An operator who wants the finding runs a capture. The monitor should say so:
when a session ends, offer "record this as a capture" rather than silently
recording it.

## Safety

Everything the capture plan says still holds, and none of it is weakened:

- the monitor's decoded path transmits nothing; the plugin has no send path,
  not even a disabled one;
- **a CAN controller in normal mode acknowledges frames it receives in
  silicon.** Attaching to a live vehicle bus is not electrically inert however
  read-only the software is. Listen-only is host link configuration and neither
  the plugin nor this screen may set it. The monitor already shows bitrate, FD
  mode, and controller state read-only (can_screen.dart `_buildLinkStatus`);
  it must also show plainly whether the selected interface is a virtual `vcan`
  before a session starts;
- the send panel keeps its current raw behavior and gains nothing from target
  selection. A screen that transmits must not acquire a definition-driven send
  path by the side door — that is the composer, with its preview digest and its
  draft-target acknowledgement;
- error frames are bus health, never traffic, and never rows. The aggregator
  already enforces this before identity is read;
- payloads are target data: not logged at info level, not in tracebacks.

## Performance

Two measured facts and one unknown.

The hardware validation ran **2355 frames in 5.01 s — roughly 470 f/s** — with
cantools decoding every frame. A busy 500 kbit bus is nearer 3000 f/s, six
times that, and the aggregator has never been run at that rate. **Benchmark
`CaptureAggregator` against a synthetic 3000 f/s source in phase 1**, before any
UI work. If it cannot keep up, that is a decoder-throughput question with its
own answers (decode on change only, decode a subset of identities, a decoder
thread) and it is much cheaper to learn now than after the screen is built.

The current monitor screen will not survive a real bus either, for reasons that
have nothing to do with decoding and must be fixed as part of this work:

- it calls `logger.info('Received message: $message')` **per frame**
  (can_screen.dart:390);
- it calls `setState` **per frame** (can_screen.dart:415), rebuilding the whole
  `DataTable` each time;
- `canMessages` is `static` (can_screen.dart:27), so it outlives the screen and
  carries stale frames into the next session;
- the 帧计数 column renders `CanData.frameCount` (can_screen.dart:141), which
  `CanData.fromJson` never assigns (can_screen.dart:576), so it is always 0.

Per-identity rows with a coalesced repaint (~10 Hz) fix the count column and
the repaint storm together, and match what the decoded view already does.

## Files expected to change

### Root repository

| File | Change |
|---|---|
| `iotsploit-exploits/src/iotsploit_exploits/canbus/live_capture.py` | `mode` in the request; monitor ceilings; cancellation callback through `capture_frames`; no observation scope in monitor mode; surface `unknown_overflowed` in snapshots. |
| `iotsploit-exploits/tests/test_can_live_capture.py` | Monitor mode: ceilings, cancellation, no observations, snapshot contents. Throughput benchmark. |
| `iotsploit-protocols/src/iotsploit_protocols/canbus/` | Bus-matching scoring moved out of `tools/` so the CLI and the API share one implementation. |
| `iotsploit-protocols/tests/` | Scoring: a clear winner, no winner, and a tie. |
| `tools/match_can_bus.py` | Reduced to a CLI front end over the shared scorer. |
| `iotsploit-django/src/iotsploit_django/view_handlers/plugin_views.py` | Route streaming runs to their own queue rather than `interactive`. |
| `iotsploit-django/src/iotsploit_django/settings/base.py` | The new queue and its routing, documented like the interactive one. |
| `iotsploit-django/src/iotsploit_django/tasks/` | Start the queue's worker alongside the others in `runserver`. |
| `iotsploit-django/src/iotsploit_django/view_handlers/` | An endpoint for Identify bus. |
| `docs/product-specs/can-live-capture.md` | Monitor versus capture: which tool answers which question. |

### Flutter repository

| File | Change |
|---|---|
| `lib/screens/tasks/components/can_screen.dart` | Target/bus/interface selection; embed `CanCaptureView` when a target is chosen; keep the raw table as the no-target mode; per-identity rows; drop the per-frame log and per-frame `setState`; un-`static` the buffer. |
| `lib/widgets/plugins/can_capture_view.dart` | A raw-payload column beside the decoded one; wire the existing `onStop`; surface `unknown_overflowed`. |
| `lib/models/can_capture.dart` | Unchanged if possible — it already merges this shape. |
| `lib/services/targets_service.dart` | Reused as-is for the target payload. |
| `test/widget/can_screen_test.dart` | No target → raw. Target → decoded. Stop. Bus fault. |
| `test/widget/can_capture_view_test.dart` | Raw column, stop, overflow notice. |

## Testing requirements

Deterministic tests only. No test opens `can0`, `vcan0`, or a socket; the
scripted frame source the capture tests already use drives everything.

- Monitor mode records no observations, and declares no scope, so no scan is
  left failed.
- Monitor mode still ends at its ceiling, and closes its socket, with no
  consumer attached.
- A cancellation raised mid-loop ends the session, closes the socket, and
  returns what was seen rather than an error.
- A cancellation that arrives after the budget is spent is not an error.
- `mode` absent behaves exactly as today, byte for byte in the result payload.
- Bus scoring: an unambiguous winner is reported as one; no bus explaining the
  traffic is reported as that and not as a low-scoring winner; a near-tie is
  reported as a tie with the advice to listen longer.
- Identity overflow appears in a snapshot, not only in the final result.
- Throughput: the aggregator sustains 3000 f/s with decode enabled, or the
  measured ceiling is recorded here and the design adjusted before phase 4.
- Flutter: no target selected renders exactly the current raw table; selecting
  a target switches to the decoded table without losing the raw payload column;
  Stop is reachable and disables itself once the session ends; a faulted bus
  shows the health strip rather than an empty table.

Both full gates apply: `tools/testing/test-python-full.sh` from the root and
`tools/testing/test-flutter-full.sh` from `ui/`.

An optional manual rehearsal on `vcan0` with `canplayer`, and then the bench
PCAN adapter, follows the deterministic suite and is never part of the commit
gate.

## Implementation phases

1. **Throughput first.** Benchmark `CaptureAggregator` at 3000 f/s with decode
   on. Exit: a number in this file, and a decision recorded if it falls short.
   Nothing else starts until this is known.
2. **Monitor mode in the plugin.** `mode`, ceilings, cancellation callback, no
   observations. Exit: every monitor-mode test passes with no socket and no
   stream; capture mode's result payload is unchanged.
3. **Queue and transport.** The streaming queue and its routing; decide the
   one-socket-versus-two question with both consumers in front of you. Exit: a
   monitor session runs for minutes without blocking an interactive prompt.
4. **Bus identification.** Shared scorer, endpoint, CLI reduced to a front end.
   Exit: all three outcomes reported distinctly.
5. **The monitor screen.** Selection, the embedded decoded view, the raw
   fallback, and the four performance fixes. Exit: widget tests cover both
   modes with no backend.
6. **Documentation and validation.** Which tool answers which question; both
   gates; `vcan0` then the bench adapter.

### Implementation record

- `CaptureAggregator` decoded 300,000 synthetic frames in 3.801 seconds on the
  development host: **78,918 frames/s**, over 26 times the 3,000 frames/s
  target. No decoder redesign was needed.
- Deviation: `SocketCanReceiver.frames()` gained an optional cancellation
  callback. A callback only in `capture_frames()` cannot run while a bus is
  silent because the iterator yields no message; without the receiver-level
  check, Stop could wait for the one-hour ceiling. The callback is checked
  after each existing bounded `recv` timeout and does not alter raw-driver or
  transmit behavior.
- Snapshot transport remains the existing dedicated
  `can_capture_<bus_id>` stream. Execution events continue to carry durable
  lifecycle state only.

## Acceptance criteria

- With a target and a bus selected, the monitor shows decoded signal values
  updating as frames arrive, with the raw payload visible beside them.
- With no target selected, the monitor is behaviorally identical to today.
- The bus is always an explicit choice, and Identify bus reports a clear
  winner, no winner, and a tie as three different answers.
- Stop ends the session promptly and closes the socket; so does the ceiling.
- A monitor session records no observations and leaves no failed scan.
- A monitor session cannot block an interactive prompt.
- `SocketCANDriver` is unchanged; the raw stream still works with no target.
- Nothing in the monitor's decoded path can transmit, and the send panel gained
  no target awareness.
- The aggregator's sustained frame rate is measured and recorded here.
- Both full gates pass; no deterministic test touches a real interface.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Decode cannot keep up on a busy bus | Measured in phase 1, before anything is built on it. Escape hatches already exist: `decode=False`, changed-rows-only emission. |
| The wrong bus is selected and every value is quietly wrong | Explicit choice, Identify bus, and the raw payload always on screen beside the decoded value. |
| A long session starves the interactive queue | Its own queue, chosen by the request; asserted by a test. |
| A session outlives the operator's attention | A duration ceiling that ends it, and a screen that says it ended rather than going quiet. |
| The monitor becomes a second, unaccountable evidence path | It records nothing, and offers the capture plugin when the operator wants a finding. |
| Two sockets on one interface (driver and session) confuse ownership | SocketCAN gives each socket its own copy; the screen must show which source it is displaying, and the send panel stays with the driver. |

## Explicit non-goals

- A Dart CAN decoder, now or later
- Modifying `SocketCANDriver`, its commands, or its raw stream shape
- Transmitting from the decoded view, or making the send panel target-aware
- Recording observations from a monitor session
- ISO-TP reassembly or UDS-over-CAN decoding
- Decoding stored capture files, or writing traffic to a log format
- Configuring interfaces, bitrate, FD mode, or listen-only
- Diffing what the monitor saw against the catalogue
- Replacing the capture plugin, or folding the two features into one

## Completion bookkeeping

While implementing, update this file with deviations and the reason for each.
When every acceptance criterion is met, add final commit IDs and test counts,
record deferred limitations, and move this plan to `docs/exec-plans/completed/`.

Completed 2026-08-25.

- Root full gate: Ruff passed; pytest **1066 passed, 0 failed, 0 skipped,
  42 warnings**.
- UI full gate: Cargo format/clippy passed; Rust **39 passed, 0 failed**;
  Dart formatted 269 files with no changes; Flutter analyzer reported **0
  issues**; Flutter **294 passed, 0 failed**.
- Pi 5 (`tkxb@10.8.0.10`) read-only validation on `can0`: the shared scorer
  identified `bus_can_bkbcanfd` as the clear winner (**25/25 identities**;
  runner-up **16/25**). A three-second cancellable monitor decoded **1352
  frames across 25 identities**, with 0 undefined, 0 undecodable, 0 error
  frames, 15 snapshots, a final snapshot, `stop_reason=cancelled`, and no
  observation scope or batch. The link remained CAN FD, ERROR-ACTIVE, with
  live tx/rx error counters at zero. No frame was transmitted by the test.
- No commits were created as part of this request, so there are no final commit
  IDs to record. Root and nested-UI changes remain in their respective working
  trees for review.
- The Pi test copied only the capture/scoring modules into the rig checkout and
  restored them immediately afterwards; it did not deploy or restart the
  running Django/Celery/UI stack.
