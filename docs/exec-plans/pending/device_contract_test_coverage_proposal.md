# Device Contract Test Coverage Proposal

## Status

- **State:** Partly implemented, 2026-09-04. Section 3.2 is written and passing;
  a software-only substitute for part of 3.1 is written and passing (section
  3.1a). Section 3.1 itself is deferred: no hardware dependency wanted for now.
  Section 3.3 is still a decision, not a test
- **Draft date:** 2026-09-03
- **Basis:** Three defects found while shipping the PCAN driver —
  `feat/pcan-device-driver` at `1f7c397` (this repo) and `dev` at `13ef1cc`
  (`iotsploit-ui`). Both are pushed; all three defects are fixed
- **Estimated effort:** ~1 day for sections 3.1 and 3.2; section 3.3 needs a
  decision before it needs effort
- **Decision owner:** User
- **Blocked on:** nothing, but see section 5 — the Flutter gate is red from
  pre-existing failures, so adding to it protects less than fixing it

**Goal.** Every one of the three defects below sat behind a gate that was
green at the time. This proposes the minimum test code that would have caught
two of them, and states plainly why the third is not a testing problem at all.

## Governing Standards

- `AGENTS.md` — **Keep scope minimal.** "Tests are out of scope by default —
  rely on existing coverage and focused validation; only an uncovered,
  high-risk regression path justifies minimal new test code." Two paths
  qualify. Everything else this incident touched is deliberately not proposed.
- `.agents/standards/testing.md` — the marker table. `hardware` is registered
  and used by **zero files** in the repository.
- `docs/writing-plugins.md` — "Take the highest rung and say which," plus a
  `django` test through the HTTP path, because "coercion and serialization
  happen only there."

## 1. What happened

Five links, each hiding the next. The order matters: fixing any one of them
was what made the following one visible.

1. **The contract moved.** `e188274` (2026-09-02) added `@require_POST` to the
   five device action views — `device_views.py:97` for `scan_specific_device` —
   and shipped `test_device_actions_reject_get` (`test_api_surface.py:37`) to
   pin it.
2. **The client never followed.** `iotsploit-ui` had sent `GET
   /api/scan_device/<driver>/` since `90e1969` (2025-01-04). From the moment
   step 1 landed, every device scan answered **405**.
3. **The failure was silent.** `_showDeviceSelectionDialog` checked
   `if (response.statusCode == 200)` with no `else`. A command button ran its
   scan, took the 405, and returned with no dialog, no message, and no log
   line — indistinguishable from a dead button. The device-count badge simply
   read zero, which looks exactly like an unplugged rig.
4. **Fixing the verb exposed the dialog.** With POST, the dialog finally
   opened — and `_selectedOption` (`unified_dialog.dart:318`) starts `null` and
   is only set by tapping a row (`:712`). Confirm pops that value (`:806`), so
   pressing **Select** without tapping first returned `null`, which every
   caller reads as "cancelled." Three clicks produced three scans in the server
   log and zero commands.
5. **Fixing the dialog would have exposed the driver.** `can-up`/`can-down`
   read `self.current_interface`, but `_handle_command`
   (`device_manager.py:606`) resolves the device straight from the scan and
   **never requires an initialize**. The request would have gone out as
   `{"iface": null}`, rejected by the daemon with a message about strings. On a
   rig with two PEAK adapters it was worse: a command aimed at `can1`
   reconfigured `can0` and reported success.

## 2. Why each gate missed it

| Defect | Gate that should own it | Why it passed anyway |
|---|---|---|
| GET vs POST | neither | The contract lives in HTTP between two repositories. Each gate tests one side; nothing crosses. |
| Dialog confirm | `test-flutter-full.sh` | The widget had exactly one test, about font styling. The gate also is not hooked up on the rig's working copy and cannot run there (section 5). |
| `current_interface` | `test-python-full.sh` | The driver tests call `initialize()` then `command()` in-process. The manager does not call `initialize` at all, so the tested lifecycle was not the real one. |

Two findings worth stating on their own:

- **The existing test described the breakage and passed.**
  `test_device_actions_reject_get` asserts `Client().get(path).status_code ==
  405` and did so every day for eight months. A test that pins server behaviour
  cannot tell you a client is still speaking the old contract. It describes the
  wall; it never sees who walks into it.
- **Zero tests POST to `/api/execute_device_command/`.** The plugin guide
  mandates a `django` test through `POST /api/execute_plugin/` — the *exploit*
  path. The device command path has no equivalent anywhere in the tree, which
  is precisely the seam defect 5 lived in.

## 3. Proposal

### 3.1 A hardware tier for the PCAN driver — deferred

**Deferred on 2026-09-04:** no hardware-dependent test wanted for now. Recorded
here because the gap is real, not because it is scheduled.

**Correction to this section as first drafted.** It proposed a
`hardware`-marked test under `tests/`. `.agents/standards/testing.md:159` says
"Never add hardware diagnostics back into a `tests/` directory," and the
precedent is `tools/hardware/manual_wifi_backend_check.py` — a manual script,
not collected by pytest, with a `--safe-only` read-only mode. So this belongs
at `tools/hardware/manual_pcan_check.py`, not in a test file. A marked test
would still be collected and skipped on every machine without an adapter; a
manual script is simply absent there, which is the better behaviour.

Sketch, whenever it is wanted, roughly 40 lines:

- scan finds a PEAK adapter, or skip with a reason naming the missing hardware;
- `can-up` → assert the kernel reports `bitrate 500000`, `dbitrate 2000000`,
  both sample points `0.750`, FD, and the link UP;
- `can-down` → assert the link is DOWN;
- restore the link to the state the test found it in.

Excluded from the commit gate by existing policy ("physical hardware tests,"
"tests that modify real network or device state"). Run on the rig with
`poetry run pytest -m hardware`.

**Why it earns its place:** this is currently verified by a human typing `ip
-details link show` over SSH, and that is the only evidence the driver has ever
worked. It would be the repository's first `hardware` test, which makes the
registered-but-unused marker real and gives the next driver a pattern.

**Risk to state, deliberately:** it raises a CAN link, so an error-active
controller ACKs on whatever bus the adapter is plugged into. That is why it is
opt-in, read-only by default, and must restore the prior link state in a
`finally`.

### 3.1a The software half of it — done

`iotsploit-drivers/tests/test_pcan_privileged_contract.py`, `contract`, 2 tests.

`FD_TIMING` is copied verbatim into a `can-fd-up` request and validated field
by field by the root daemon, so a renamed key or an out-of-range sample point
is a driver that raises no link — and the only place that showed up was on the
bench. These tests push the driver's own constant through the daemon's real
validator and assert the exact `ip` argv that comes out.

That covers the "does the daemon accept this request" half without hardware.
The remaining half — whether a PEAK controller accepts the timing against its
own clock and tseg ranges — is a property of silicon and has no software
substitute. `vcan` cannot stand in: the daemon rejects it for `can-fd-up`
because a virtual interface has no bit timing.

Verified by mutation: changing `dsample_point` to 0.99 fails the argv test;
renaming it to `dsamplepoint` fails both.

### 3.2 A device-command path test — done

`iotsploit-django/tests/test_device_command_path.py`, 6 tests, marked
`contract` rather than `django` to match `test_api_surface.py`, which covers
the same view module. A real `DeviceDriverManager` carrying one stub driver;
only the driver is fake, because a mocked manager would assert nothing about
the lifecycle, which is where the defect was. It asserts the three rules that
defect 5 broke:

1. a command reaches the driver **with no initialize call anywhere** in the
   sequence;
2. the driver receives the device whose `device_id` was requested — proven with
   two devices registered, not one;
3. an unknown `device_id` returns a structured error, not a 500;

plus three the incident implied: a command before any scan reaches no driver,
`GET /api/execute_device_command/<driver>/` is 405 (the route defect 1 broke,
which `test_device_actions_reject_get` never listed), and a command naming an
absent driver does not reach a different one.

Verified by mutation: making the manager call `initialize` before a command
fails rule 1; making it fall back to the first registered device when
`device_id` misses fails rule 3, which is the two-adapter symptom.

**Why it earns its place:** it encodes the manager's actual contract at the
seam where drivers meet it. The driver-level version of rule 2 now exists
(`test_a_link_command_acts_on_the_device_it_was_addressed_to`), but it only
protects *this* driver. The next author reaching for `self.current_interface`
is caught by this test instead of by a vehicle.

### 3.3 The cross-repo verb contract — not a test problem

Each Dart call site uses `package:http` directly, so there is nothing
injectable to assert against. Three honest options:

- **(a) Centralise the device API** in one Dart service with an injectable
  client, then unit-test the verbs. The proper fix — but a refactor across
  about six screens, not a test.
- **(b) An `integration_test/` smoke** driving the app against a live backend.
  Catches it truthfully; needs a running server, so it cannot join the
  deterministic gate.
- **(c) A source-scanning test** (~20 lines): fail if any `http.get` targets a
  path the server serves POST-only. Brittle and inelegant, and it would have
  caught exactly this bug.

**Recommendation:** (c) now as a stopgap, (a) when the UI's API surface is next
touched for other reasons. What no test fixes is the shape of the problem: one
side changed a contract, and the only enforcement lived in the repo that made
the change.

## 4. What this deliberately does not propose

- No further unit tests for driver internals — `test_drv_pcan.py` covers scan,
  validation, addressing, and link commands, and four of its ten tests fail
  against the pre-fix driver.
- No mocking beyond the seams already used (the privileged helper, and `ip`
  output recorded from the bench Pi).
- No CI infrastructure for end-to-end runs. That is a larger decision than this
  incident justifies.

## 5. Prerequisite: the Flutter gate is red

`tools/testing/test-flutter-full.sh` on the rig:

- **Cannot run at all there.** It begins with three `cargo` steps and cargo is
  not installed on the Pi. Steps 4–6 (format, analyze, test) were run by hand
  for the fixes in `13ef1cc`.
- **Six tests fail** in `test/unit/explorer_graph_layout_test.dart`, reproduced
  identically with the fixes stashed (`+25 -6` either way), so they predate
  this work.
- The hook is not enabled on that working copy — `git config core.hooksPath` is
  unset, so nothing runs the gate automatically.

Until those three are resolved, the Flutter gate protects nothing on the rig,
and section 3.3's stopgap would not run either. **Fixing this precedes adding
to it.**

## 6. Order and effort

| # | Item | Effort | Gate |
|---|---|---|---|
| — | 3.2 device-command path test | done 2026-09-04 | `test-python-full.sh` |
| — | 3.1a FD timing / daemon verb contract | done 2026-09-04 | `test-python-full.sh` |
| 1 | Decide the owner of the nested-`args` defect (section 8) and fix it | ~1 h | `test-python-full.sh` |
| 2 | Repair the 6 `explorer_graph_layout_test` failures; enable the hook; install cargo on the rig or split the Rust steps | unknown until diagnosed | unblocks the Flutter gate |
| 3 | 3.3(c) source-scanning stopgap | ~1 h | `test-flutter-full.sh` |
| 4 | 3.3(a) centralised Dart API service | ~1 day | `test-flutter-full.sh` |
| — | 3.1 PCAN bench script | deferred, no hardware dependency wanted | manual |

## 7. Decisions already taken

- **`scan_device` stays POST-only.** Considered allowing GET so that
  already-installed app builds keep working. Rejected: the FT2232 and Ubertooth
  scans open the device to read string descriptors, so a scan is hardware I/O
  and cannot honour GET's promise of being safe to prefetch, cache, or retry.
  The client was the side that was out of date, and it has been fixed
  (`iotsploit-ui` `7bf77c7`).
- **Initialize no longer raises the CAN link.** `/api/initialize_devices/`
  initializes and connects every device of every enabled driver; with the
  original driver that put a controller on a live bus as a side effect of what
  reads like an inventory step. Raising and lowering the link are now explicit
  `can-up`/`can-down` commands (`1f7c397`).

## 8. Found while writing section 3.2: command args arrive nested

Not a test problem, and not fixed here — it needs a decision about whose
contract is wrong.

`execute_device_command` reads `args` out of the JSON body and passes it as
`execute_command(..., args=args)`. `execute_command` takes `**kwargs` and
forwards `args=kwargs`, so what reaches the driver is one level deeper than
what the client sent:

```
client sends : {'id': '123', 'data': 'deadbeef'}
driver gets  : {'args': {'id': '123', 'data': 'deadbeef'}}
```

`SocketCANDriver._command_send` reads `args['id']` directly, so a `send` issued
from the UI has never worked through this endpoint — it fails with "send
requires a CAN id". No driver in the tree compensates for the nesting; the
Django view is the only caller of `execute_command`. The PCAN work did not hit
it because `can-up` and `can-down` take no arguments.

Two candidate owners, and they are not equivalent:

- **The view.** `execute_command(..., **args)` matches the manager's `**kwargs`
  signature, which reads as "the keyword arguments *are* the command args."
  But `can_screen.dart` sends `args` as a **string**, and `**` on a string
  raises.
- **The manager.** `args=kwargs.get('args', kwargs)` would accept both shapes,
  at the cost of a signature that means two things.

Whichever is chosen, `args` needs a stated type in the HTTP contract first —
object or string — because the Dart call sites currently disagree with each
other. That is the same shape of problem as section 3.3: two repositories, one
contract, enforcement in only one of them.
