# CAN Work — Implementation Checklist

Working tracker for two accepted-or-pending plans. Detail lives in the plans;
this file is the ordered set of things to tick off.

- Composer: [`can_frame_composer_plugin_plan.md`](can_frame_composer_plugin_plan.md) — accepted 2026-08-24
- Capture: [`can_live_capture_plan.md`](can_live_capture_plan.md) — **drafted, not yet accepted**

Two repositories, committed and merged independently: the root IoTSploit repo
and the nested `ui/` Flutter repo.

## Gate before every commit

```bash
tools/testing/test-python-full.sh      # from root
tools/testing/test-flutter-full.sh     # from ui/
```

Report passed / failed / skipped / warnings / analyzer counts. Never `--no-verify`,
never weaken an unrelated test to land a change.

## Dependency between the plans

Capture consumes the composer's catalogue, reconstructed `cantools` definitions,
and `decode_frame` **unchanged**. It must not start before **composer phase 2
exits** — otherwise those get written twice against the same definitions.

It does **not** need composer phases 3–7. Once C2 is green, capture phases K1–K3
may run in parallel with composer C3–C7.

```
C1 → C2 ─┬─→ C3 → C4 → C5 → C6 → C7
         └─→ K1 → K2 → K3 → K4 → K5     (needs capture plan accepted first)
```

---

## Pre-work

- [ ] Accept or reject the live capture plan. Until accepted, K1–K5 are not startable.
- [ ] Decide whether to amend the composer contract with `operation: "decode"`
      (one-shot bytes → signals, no I/O). Cheap once C2 lands, absent from both
      plans today. Decide **after** C2, not now.

---

## Composer C1 — Freeze contracts with tests

- [ ] Target fixtures: bus-owned ARXML frame; component CAN-facet frame; same
      numeric ID on two buses; standard + extended variants of one ID; simple
      multiplexed frame; conflicting duplicate; CAN-FD frame
- [ ] Request/response contract tests written **before** implementation
- [ ] v1 request schema and error keys recorded in the product guide

**Exit:** failures describe missing behavior, not implementation names.

## Composer C2 — Pure catalogue and encoder ← *capture unblocks here*

Ordering inside this phase is load-bearing. Storage must be able to *hold* the
fields before the encoder is written against them.

### C2a — Widen stored shape first (Django)

- [ ] `tools/can_facet.py`: add `choices` + `multiplexer_signal` to `CanSignal`
- [ ] `tools/can_facet.py`: add float/decimal encoding metadata to `CanSignal`
- [ ] `tools/can_facet.py`: add `is_fd` to `CanMessage`
- [ ] `tools/can_facet.py`: add `contained_messages` at least enough to *detect
      and reject* a container frame
- [ ] `tools/can_facet.py`: set `extra="allow"` on both models (today's default
      `extra="ignore"` silently drops unknown keys on load, unlike `Facet` itself)
- [ ] `tools/dbc.py`: parse `VAL_` tables — currently `SG_` only, so DBC import
      produces **no choices at all**. Unattachable tables are dropped with a
      warning, never guessed
- [ ] **Not in either plan:** flag that existing targets imported before this fix
      lost their choices *at import time*. `extra="allow"` does not recover them —
      those targets need re-importing. Document it in the operator guide

### C2b — Protocol layer

- [ ] `iotsploit_protocols/canbus/` package created (does not exist yet)
- [ ] Immutable target CAN definitions
- [ ] `catalog.py`: resolve both storage locations; dedupe identical; mark
      conflicts; never mutate the target snapshot
- [ ] Frame-ID range validation (standard `0..0x7FF`, extended `0..0x1FFFFFFF`)
- [ ] `codec.py`: reconstruct cantools conversions, choices, multiplexing
- [ ] `autosar/arxml.py`: preserve any remaining lossless signal fields
      (parser already exists and is rich — touch-up only, **do not write a second one**)
- [ ] `codec.py`: strict encode, `scaling=True, strict=True`, canonical normalized output
- [ ] `codec.py`: `decode_frame` — branch chosen **from received bytes**; choices
      decode to labels with raw preserved; length mismatch stated not silently
      padded; uncovered bits ignored; never raises on bad wire data

**Exit:** all classic / extended / FD / endian / signed / scaled / choice /
multiplexed / wide-value / missing-value / range / conflict tests pass with no
socket import and no I/O, **and every fixture survives an encode→decode round
trip**. Component-owned resolution asserted through a *round-tripped facet*, not
a hand-built dict.

## Composer C3 — SocketCAN client and thin plugin

- [ ] `socketcan.py`: one-shot client, injected/mockable bus factory,
      `ignore_config=True`, channel-name validation, no bitrate/link mutation,
      `shutdown()` on every exit path, lazy transport import
- [ ] Object-or-JSON-string request normalization (one validation path after)
- [ ] Preview response + **canonically serialized** digest (sorted keys, fixed
      numeric repr — incidental dict ordering would make this an intermittent
      refusal to transmit)
- [ ] Policy gates: digest match, draft-target override, exactly one send, no retry
- [ ] `RequiresRoot: False` — load-bearing. The root path reduces the target to
      scalars and would strip `buses`/`components` entirely
- [ ] Entry point registered in `iotsploit-exploits/pyproject.toml`
- [ ] `python-can >=4.5` added to `iotsploit-protocols/pyproject.toml`; `poetry.lock` updated

**Exit:** preview cannot open a bus; transmit impossible without matching digest;
flags and shutdown asserted with fakes. No deterministic test touches `can0`/`vcan0`.

## Composer C4 — Exact target execution contract

- [ ] Side-effect-free `TargetManager` lookup by ID; point existing `get_target`
      scan at it rather than leaving a duplicate
- [ ] `plugin_views.py`: optional top-level `target_id`, branching **before** the
      auto-select block at `plugin_views.py:291-301` — an added lookup alone is
      not sufficient, the existing code calls `set_current_target()` as a side effect
- [ ] Absent-ID behavior preserved for existing callers (auto-select included)
- [ ] Flutter always sends `target_id`; MCP `execute_plugin` gains the same optional arg
- [ ] Contract tests + docs updated

**Exit:** two clients on different targets cannot make the composer act on the
wrong one. Tested **with no current target set at all**, which must run the
plugin and leave current target unset.

## Composer C5 — Shared Flutter input architecture

- [ ] Extract duplicated `_showParameterDialog` / `_promptParameters`
- [ ] Dispatch on declared parameter **type**, never on plugin name
- [ ] Pure Dart CAN catalogue; delegate existing `TargetModel` enumeration rather
      than creating a second divergent traversal
- [ ] All existing plugin forms behaviorally unchanged

**Exit:** both screens use one path; ordinary plugin widget tests still pass.

## Composer C6 — Composer UI and preview/send flow

- [ ] Lazy full-target load on open, with loading / error / retry / deleted states
- [ ] Bus + frame search (name, decimal ID, hex ID); conflicted and unsupported
      rows disabled with reasons; lazy/virtualized lists
- [ ] Channel selector reads the existing device scan; sends `interface` (`can0`)
      **not** `device_id` (`can_001`); must not initialize or connect the driver;
      empty scan explains itself
- [ ] Typed signal rows: multiplexer first, choices as dropdown, wide/signed as
      text (no Dart `int` coercion), per-signal error state
- [ ] Preview rendering; **any** edit invalidates the digest and disables Transmit
- [ ] Draft acknowledgement independent and explicit; danger confirmation repeats
      target, channel, frame, payload
- [ ] No `setState` after dispose when closed mid-request
- [ ] New reusable pieces added to Component Showcase (required by `ui/AGENTS.md`)

**Exit:** widget tests exercise the whole state machine with no backend and no CAN interface.

## Composer C7 — Documentation and validation

- [ ] `docs/product-specs/can-frame-composer.md` — Flutter, direct API, MCP, CLI JSON
- [ ] Document external `vcan0`/`can0` setup without embedding privileged setup
- [ ] Both full gates green
- [ ] Optional manual `vcan0` check, only after the deterministic suite passes
- [ ] Commit and merge root + Flutter independently

---

## Capture K1 — Receiving client

*Blocked on C2 exit and on the capture plan being accepted.*

- [ ] Bounded receive in the **same** `socketcan.py` as the sender (sibling, not a
      second transport module)
- [ ] Injected bus factory; duration **and** frame budget, whichever ends first
- [ ] Guaranteed shutdown on success, budget exhaustion, error, and cancellation

**Exit:** lifecycle asserted with fakes only.

## Capture K2 — Aggregator and decode

- [ ] Build identity→definition index **once** before the loop; reconstruct each
      cantools message once (rebuilding per frame at kHz rates drops frames)
- [ ] Test `is_error_frame` **before** reading identity — never let one reach the
      aggregator, frame table, or an observation
- [ ] Decode error class + `CAN_ERR_CRTL` `data[1]` into a separate bus-health
      tally (reuse `iotsploit_drivers.socketcan.can_errors`)
- [ ] `is_remote_frame` as its own category, not a zero-length data frame
- [ ] Per-identity aggregation: count, first/last seen, inter-arrival stats, last payload
- [ ] `period_ms` **measured** from arrival times, never copied from declared cycle time
- [ ] Decode failures counted per identity with first reason kept; never raise,
      never log per frame
- [ ] Undefined frames counted `known: false`; cap distinct unknown identities and
      flag on overflow
- [ ] Conflicted definitions counted but never decoded

**Exit:** every aggregation and decode-failure test passes over a scripted frame
source, with no socket and no stream.

## Capture K3 — Plugin, streaming, observations

- [ ] Entry point `can_live_capture` registered
- [ ] `StreamType.CAN` on a channel owned by this run, **distinct** from the
      driver's device-ID channel
- [ ] One snapshot per `snapshot_interval_ms`, changed rows only, rate fixed by
      request not by frame rate; receive loop never blocks on broadcast
- [ ] One `ObservationBatch` per bus, scope key names the bus
- [ ] Facts in the seeder's shape: `protocol="can"`, `subject_kind="message"`,
      `subject_id=canonical_frame_id(...)`, `observed_property="seen"`, value with
      `name`/`count`/`period_ms`/`dlc` plus new `known`/`decode_errors`
- [ ] `is_complete=False` in v1 — a window is a sample, not a census
- [ ] `RequiresRoot: False`; payloads never logged at info or into tracebacks
- [ ] Correct behavior both async (`duration_s > 5`) and synchronous (how tests drive it)

**Exit:** scan lifecycle recorded on success *and* failure; snapshot cadence
independent of frame rate.

## Capture K4 — Flutter capture view

- [ ] `lib/models/can_capture.dart` — row view models, snapshot merge
- [ ] `lib/widgets/plugins/can_capture_view.dart` — live table, totals, stop, summary
- [ ] Show whether the selected interface is virtual (`vcan`) **before** capture starts
- [ ] `can_screen.dart` unchanged — add a code note explaining why the raw,
      target-agnostic view stays

**Exit:** widget tests cover a full run with no backend.

## Capture K5 — Documentation and validation

- [ ] `docs/product-specs/can-live-capture.md`
- [ ] Operator guide states plainly that a **normal-mode controller ACKs on the
      bus at hardware level** — attaching to a live vehicle bus is not electrically
      inert whatever the software does. Listen-only is host link config this
      plugin must not set
- [ ] Reduce `tools/seed_can_observations.py` to a fixture generator, or retire it
- [ ] Both gates; optional `canplayer` → `vcan0` replay outside the commit gate

---

## Standing constraints

- Never modify `drv_socketcan`, its commands, its lifecycle, or `can_screen.dart`.
  The raw screen is the fallback that works with **no target selected**.
- Never write a second ARXML parser. `iotsploit_protocols/autosar/arxml.py` exists.
- No `sudo`, no `ip link`, no bitrate or link-state change anywhere in either feature.
- Nothing in the capture path can transmit — not even a disabled path.
- Transmit records **no** observation. Sending is an action, not evidence.
- Never claim local send success means an ECU received or acted on the frame.
- Fuzzer `python-can` wrappers stay untouched in v1.

## Bookkeeping

Record deviations and their reason in the plan files as you go — never silently
change the request schema or the safety flow. On completion, add commit IDs and
test counts, record deferred limitations, and move both plans to
`docs/exec-plans/completed/`.
