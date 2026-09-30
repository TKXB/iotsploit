# Target monitors: one monitor set for every signal

**Status (2026-09-30): Phases 0–2 implemented and verified on hardware; Phase 3 not started.
Nothing committed yet.** See §10 for what was built, where it differs from the text
below, and what remains unverified.

Design artifact: `ui/docs/design/iotsploit_monitor_architecture_comparison.html`
(diagrams, change map, P&A rings). This plan is the executable version of that page;
where they disagree, this file wins and the page gets fixed.

Spans two repositories:

| Repo | Path | Holds |
|---|---|---|
| root | `/` | Python packages: `iotsploit-core`, `-fuzzer`, `-drivers`, `-django` |
| ui | `ui/` (nested git repo) | Flutter app, Rust bridge (`ui/rust`), boundary-scan crates (`ui/jtag`) |

Every step below names its repo. Commits never span both.

---

## 0. Decisions (locked)

1. **Python owns every target monitor.** JTAG core health now; UART, voltage and BLE next.
2. **Boundary scan stays in Rust** (`ui/rust/src/api/jtag.rs`, probe-rs). It is not a
   monitor and is not ported. It shares exactly one thing with Python: the resource lock.
3. **Monitors are multi-kind.** The cross-layer type is a kind-neutral envelope
   (`MonitorObservation`) with a per-kind `detail`. No core-specific type crosses a layer.
4. **Sampling and judgement are separate.** Sources (in core) turn hardware into
   observations. Policies (in the fuzzer) turn observations into verdicts.
5. **Ports and adapters** per `docs/architecture.md`: interfaces in `iotsploit-core/ports`,
   services in `iotsploit-core/core`, adapters chosen only in
   `iotsploit_django/composition_root/core_container.py`.
6. **`iotsploit-fuzzer` keeps zero dependency on `iotsploit-core`.** It handles
   observations as plain dicts and receives sources as bound methods.
7. **The JTAG core kind is named `mcu_core`**, the value already on the wire
   (`views_campaign.check_mcu_core` returns `"kind": "mcu_core"`).

## 1. Current state (verified 2026-09-30)

| Concern | Where | Fact |
|---|---|---|
| Session | `iotsploit-django/.../tools/iot_protocol_runtime.py:25` `CoreMonitorSession` | Validates config, hardcodes `NRF52840_XXAA` / `NRF5340_XXAA_APP`, digits-only serial, constructs `JLinkAbility()` directly, in-process lock `_core_probe_owners` keyed by serial. No Django imports. |
| Driver | `iotsploit-drivers/.../jlink/drv_jlink.py` | `core_status` / `fault_snapshot` / `recover_target` mix pylink transport, Cortex-M decoding (DHCSR read-to-clear, CFSR/HFSR/ICSR) and Nordic `RESETREAS`. `_TARGETS` holds `cpuid_part`, `resetreas`, `ram` per target. |
| Harness | `iotsploit-fuzzer/.../harnesses/jtag_harness.py` | Wraps one inner harness with one `observe` callable. Persistent-fault rule hardcodes exceptions `(3,4,5,6)`. Recovery budget, expected-reset prefixes, snapshot on failure. |
| Wiring | `iot_protocol_runtime.py:313-352` | Builds session + `JtagHarness` from `campaign_config["core_monitor"]`; preflight consumes a first `reset` sample; emits `core_status` event with `core_observation`. |
| Events | `iot_protocol_runtime.py:554-563` | Any event carrying `core_observation` is recorded and stored via `IoTFuzzerManager.update_campaign_state`. |
| History | `CoreObservationRecorder` | `source="iot-fuzzer-jtag-core-monitor"`, scope `jtag-core:{target}:{serial}`, `Fact(protocol="jtag", observed_property="core_state")`, through the `ObservationSink` port. |
| REST | `views_campaign.check_mcu_core`, route `iot-fuzzer/monitors/mcu-core/check/` | Accepts `{"monitor": {...}}` or the bare config; returns `{"monitor": {"id": "mcu-core", "kind": "mcu_core", "observation": …}}`; 409 on busy probe. |
| Flutter | `ui/lib/screens/iot_fuzzer/controllers/test_controller.dart`, `widgets/monitor_workspace.dart` | Sends `probe_serial`, `target_device`, `target_id`, reset prefixes. Reads `state`, `observed_at`, `stop_reason`, `detected_reason` from `coreObservation`; the rest is shown as JSON. Target dropdown hardcodes the two nRF values. |
| Boundary scan | `ui/rust/src/api/jtag.rs`, `ui/jtag/crates/jtag-probe` | Opens probes via probe-rs in the Flutter process. No lock shared with Python. |
| Other "monitors" | `iotsploit-fuzzer/.../monitoring/monitor.py` (`BaseMonitor`), `boundary_monitor.py` (`BoundaryMonitor`), `tools/monitor_mgr.py` (`DeviceMonitor`, unused `MCUMonitor`) | None watch the target. Untouched except `MCUMonitor` (deleted). |
| UART transport | `iotsploit-fuzzer/.../interfaces/uart_interface.py` | The UART *protocol* harness opens the serial port itself. |
| Tests | `iotsploit-fuzzer/tests/test_jtag_harness.py` (10), `iotsploit-drivers/tests/test_jlink_core_status.py`, `iotsploit-django/.../tests/test_iot_fuzzer_responses.py` (2 MCU tests, session patched out) | Nothing exercises session construction or the event/recorder path end to end. |
| Hardware | J-Link rig on 10.8.0.14 | nRF52840. No nRF5340 bench is known. |

## 2. Target design

### 2.1 Observation envelope — `iotsploit-core/domain/monitoring.py`

```python
Health = Literal["ok", "degraded", "fault", "down", "reset", "unavailable"]

class MonitorObservation(TypedDict):
    monitor: str                 # plan-entry name, unique per campaign: "mcu_core:app", "uart:console"
    kind: str                    # "mcu_core" | "uart" | "power" | "ble"  (open set)
    resource: str                # lease key, §2.6
    target: str
    window: tuple[float, float]  # (start, end) wall-clock; point samples: start == end
    observed_at: float           # == window[1]
    health: Health               # source's kind-neutral reading
    reasons: list[str]           # human-readable causes (was fault_causes)
    detail: dict                 # exactly one *Detail, chosen by kind

class McuCoreDetail(TypedDict):  # today's observation minus envelope fields
    core: str                    # "main" for single-core targets, "app"/"net" for nRF5340
    state: str                   # running|sleeping|halted|fault|lockup|reset|unavailable
    active_exception: int | None
    arch: dict                   # {"cortex_m": {"dhcsr": …, "cfsr": …, "hfsr": …, "icsr": …}}
    vendor: dict                 # {"nordic": {"resetreas": …}}
    snapshot: dict | None        # fault_snapshot output when captured

class UartDetail(TypedDict):     # P3
    port: str; baud: int; bytes: int; tail: list[str]; matches: list[dict]
    boot_banner: bool; artifact: str | None

class PowerDetail(TypedDict):    # P3
    rail: str; v_min: float; v_max: float; v_mean: float; i_max: float | None; samples: int

class BleDetail(TypedDict):      # P3
    address: str; adverts: int; last_advert_age_ms: int | None; rssi: int | None; connectable: bool
```

Rules:

- A verdict is **not** in the observation. `crashed`, `stop_reason`, `detected_reason`,
  `expected_reset`, `recovery`, `before`, `confirmation` belong to the verdict (§2.3).
- `detail` is bounded: UART `tail` ≤ 50 lines, power arrays are summary stats only.
  Full captures are written as artifacts and referenced by path.
- Adding a kind never adds an envelope field.

### 2.2 Sources — `iotsploit-core/core/monitoring/`

```python
class MonitorSource(Protocol):
    kind: str
    resource: str
    settle_ms: int
    def open(self) -> None: ...
    def begin(self) -> None: ...                 # window sources start/mark buffering
    def end(self) -> MonitorObservation: ...     # point: sample now; window: summarise since begin()
    def recover(self, expected: bool) -> dict: ...
    def close(self) -> None: ...
```

- `source.py` — the Protocol plus `SourceRegistry` (kind → factory). Factories are
  registered by the composition root, never by core.
- `service.py` — `MonitorService`: validates a plan (§2.5), opens one source per entry,
  acquires each resource's lease, guarantees `close()` + release on every exit path,
  and serves the one-shot manual check for any kind.
- `sources/mcu_core.py` — `McuCoreSource` (point). Composes a `DebugAccess` backend
  (private instance from `DeviceDriverManager.get_driver_class()`), an arch monitor and a
  `TargetProfile`.
- `arch/cortex_m.py` — the only code that reads DHCSR. Status, fault snapshot, recovery
  baseline, written against `DebugAccess`.
- `target_catalog.py` + `resources/targets/nordic.toml` — profiles as data
  (`arch`, `cores`, `cpuid_part`, `ram`, `vendor_registers`).

### 2.3 Judgement — `iotsploit-fuzzer`

```python
class MonitorVerdict:            # monitoring/target_monitor.py
    monitor: str
    verdict: Literal["ok", "crash", "hang", "expected_reset"]
    stop_reason: str | None
    detected_reason: str | None
    decisive: bool               # False = corroborating evidence only
    observation: dict            # MonitorObservation, opaque except envelope keys
    recovery: dict | None

class TargetMonitor(Protocol):
    name: str
    settle_ms: int
    def preflight(self) -> MonitorVerdict: ...   # campaign start; may consume stale state
    def before(self) -> MonitorVerdict: ...
    def after(self, payload: bytes) -> MonitorVerdict: ...
    def recover(self, expected: bool) -> bool: ...
```

- `harnesses/monitor_set_harness.py` — `MonitorSetHarness(inner, monitors)`. Per case:
  every `before()` → payload → sleep `max(settle_ms)` → every `after()` → combine →
  recover if needed. Severity `crash > hang > expected_reset > ok`; only `decisive`
  verdicts can stop a campaign; a reset is `expected_reset` only if every monitor that
  saw it agrees. `stop_reason` is prefixed with the monitor name.
- `monitors/mcu_core.py` — `McuCoreMonitor`: today's `JtagHarness` policy
  (persistent-fault confirmation, recovery budget, expected-reset prefixes, snapshot on
  failure), reading `health`, `reasons`, `detail.state`, `detail.active_exception`.
  Preflight keeps the "consume one stale `reset`" rule.
- P3: `monitors/uart_log.py`, `power.py`, `ble_liveness.py`.

### 2.4 Ports — `iotsploit-core/ports/`

| Port | Methods | Phase | First adapter |
|---|---|---|---|
| `DebugAccess` | `architectures()`, `read_mem32(core, addr)`, `read_reg(core, name)`, `halt/resume(core)`, `reset(halt=False)` | P2 | `JLinkAbility` (pylink) |
| `ResourceLeasePort` | `acquire(resource, owner)`, `release(resource, owner)`, raises `ResourceBusyError(holder)` | P2 | `FileResourceLease` |
| `SerialLink` | `read(timeout) -> bytes` | P3 | pyserial, or a tap on the fuzzer's `UARTInterface` |
| `PowerSense` | `measure(channel) -> (volts, amps)`, optional datalog | P3 | SCPI (instrument TBD) |
| `BleObserver` | `watch(address, on_advert)` | P3 | bleak |

`DebugAccess` has no fault logic. Anything architecture-specific lives in `arch/`.

### 2.5 Wire formats

**Campaign config** (P2; `core_monitor` stays accepted, §3):

```json
"monitors": [
  {"kind": "mcu_core", "name": "mcu_core:main", "resource": "usb:1366-123456789/debug",
   "target": "NRF52840_XXAA", "target_id": "…",
   "options": {"cores": ["main"], "recovery_policy": "stop", "max_recoveries": 3,
               "expected_reset_prefixes": ["ff"], "boot_timeout_ms": 5000, "settle_ms": 20}},
  {"kind": "uart", "name": "uart:console", "resource": "serial:0403-A50285BI",
   "options": {"baud": 115200, "crash_patterns": ["HardFault", "panic"], "boot_banner": "Booting"}}
]
```

**WebSocket** (P1): new event field `monitor_observation`
`{monitor, verdict, stop_reason, detected_reason, observation}` on the existing
`fuzzer_event` channel. `core_observation` keeps being emitted for `mcu_core` (§3).

**REST** (P2): `POST /api/iot-fuzzer/monitors/<kind>/check/` → response shape unchanged:
`{"status": "success", "monitor": {"id", "kind", "observation"}}`.
`/monitors/mcu-core/check/` stays as an alias.

### 2.6 Resource lease

- Key: `<bus>:<id>/<function>`.
  - JTAG/SWD: `usb:<vid 4-hex>-<serial>/debug` (J-Link VID `1366`).
  - J-Link VCOM UART: `usb:1366-<serial>/vcom`; plain USB-UART: `serial:<vid>-<usb serial>`
    (fallback `serial:<device path>` when there is no USB serial).
  - Instrument: `scpi:<idn serial>/<channel>`; BLE: `ble:<hci name>`.
- Serial normalisation: decimal without leading zeros. Must produce the same string from
  pylink and from probe-rs `serial_number` (verify, §7 Q2).
- Lock file: `<lockdir>/<key with / and : replaced by _>.lock`, content = holder JSON
  (`pid`, `process`, `owner`, `since`) for busy messages.
  - Linux: `$XDG_RUNTIME_DIR/iotsploit/locks`, fallback `/tmp/iotsploit-$UID/locks`.
  - macOS: `~/Library/Caches/iotsploit/locks`. Windows: `%LOCALAPPDATA%\iotsploit\locks`.
- Python: `fcntl.flock(LOCK_EX|LOCK_NB)` / Windows `msvcrt.locking` — no new dependency.
  Rust: `std::fs::File::try_lock` (Rust ≥ 1.89) or the `fs4` crate.
- The OS releases the lock when the process dies. No stale-lock cleanup code.
- Takers: `MonitorService`, `DeviceDriverManager.initialize_device`, Rust `jtag_open`.

## 3. Compatibility contract (must hold through P1 and P2)

The current Flutter build and existing target history must keep working until P3 ends.

| Surface | Kept | Removed in |
|---|---|---|
| Campaign config `core_monitor` object | Translated into a one-entry `monitors` plan | P3 (after Flutter sends `monitors`) |
| `POST /monitors/mcu-core/check/` + response shape | Alias of `/monitors/mcu_core/check/` | never (cheap) |
| Event key `core_observation` | Emitted for the `mcu_core` monitor, **flattened**: `detail.*` and verdict fields at top level, so `state`, `observed_at`, `stop_reason`, `detected_reason`, `expected_reset`, `crashed` keep their current meaning | P3 |
| `update_campaign_state(..., {"core_observation": …})` | Same flattened dict | P3 |
| Target history | Source `iot-fuzzer-jtag-core-monitor`, scope `jtag-core:{target}:{serial}`, `Fact(protocol="jtag", observed_property="core_state")` for `mcu_core` | never — changing them breaks "what changed since the last scan" |
| HTTP 409 on busy probe | `ResourceBusyError` → 409 with holder text | never |

One function owns the flattening: `iotsploit_django/tools/monitor_compat.py::legacy_core_observation(verdict)`.
It is unit-tested against a recorded current payload (captured before P1 starts).

## 4. Phases

Each phase ships alone, keeps the J-Link + nRF52840 flow working, and passes the gate
(§5). Commit sizes are targets, not rules.

### Phase 0 — Baseline (root + ui, no behaviour change)

| # | Repo | Work | Done when |
|---|---|---|---|
| 0.1 | root | Record golden payloads: one `core_status` event, one manual-check response, one target-history fact, from the rig (10.8.0.14, nRF52840). Store under `iotsploit-django/.../tests/fixtures/monitor_legacy/`. | Fixtures committed; a test loads them. |
| 0.2 | root | Characterisation test for the runtime path: build the campaign runtime with a fake `JLinkAbility`, run 3 cases (ok, persistent fault, expected reset) and assert emitted events + recorder facts equal the fixtures' shape. | Test fails if any compatibility key in §3 changes. |
| 0.3 | — | Answer §7 Q1 (nRF5340 bench?) and Q2 (probe-rs vs pylink serial). | Answers written into §7. |

### Phase 1 — Envelope and monitor set (root only)

| # | Package | Files | Work |
|---|---|---|---|
| 1.1 | core | `domain/monitoring.py` (new) | `MonitorObservation`, `Health`, `McuCoreDetail`. Import-only test in `tests/test_core_imports.py`. |
| 1.2 | drivers | `jlink/drv_jlink.py`, `tests/test_jlink_core_status.py` | `core_status` returns the envelope (`kind="mcu_core"`, `detail=McuCoreDetail`). Verdict-ish fields (`crashed`, `stop_reason`) move out; `health`/`reasons` replace them. Update tests. |
| 1.3 | fuzzer | `monitoring/target_monitor.py` (new) | `TargetMonitor`, `MonitorVerdict`. |
| 1.4 | fuzzer | `monitors/__init__.py`, `monitors/mcu_core.py` (new) | `McuCoreMonitor` built from `observe/snapshot/recover` callables; port the `JtagHarness` policy. Persistent-fault confirmation compares `health == "fault"` + identical `reasons`, and `detail.active_exception` when present. |
| 1.5 | fuzzer | `harnesses/jtag_harness.py` → `harnesses/monitor_set_harness.py` | `MonitorSetHarness(inner, monitors)`; `HarnessResult.core_observation` → `monitor_verdicts: list` (keep `core_observation` property returning the `mcu_core` one). Export in `__init__`. |
| 1.6 | fuzzer | `tests/test_jtag_harness.py` → `test_monitor_set_harness.py` + `test_mcu_core_monitor.py` | Port all 10 tests. Add: two monitors, one crash one ok → crash wins with named `stop_reason`; corroborating-only crash does not stop; mixed expected-reset disagreement → not expected. |
| 1.7 | django | `tools/iot_protocol_runtime.py`, `tools/monitor_compat.py` (new) | Wiring builds `MonitorSetHarness([McuCoreMonitor(...)])` from the existing `core_monitor` config. Preflight via `monitor.preflight()`. Emit `monitor_observation` **and** `legacy_core_observation(...)`. |
| 1.8 | django | `tools/iot_protocol_runtime.py` | `CoreObservationRecorder` → `MonitorObservationRecorder` keyed by monitor; `mcu_core` keeps the §3 source/scope/fact names. Other kinds: source `iot-fuzzer-monitor`, scope `<kind>:<target>:<resource>`, `Fact(protocol=<kind>, observed_property="health")`. |
| 1.9 | django | `tools/monitor_mgr.py` | Delete `MCUMonitor` and the `"mcu"` branch of `SystemMonitor.create_monitor`. |

Exit: 0.2 characterisation test green unchanged; manual check + one campaign on the rig
produce the same Flutter display as before.

### Phase 2 — Sources, ports, shared lease (root, then ui)

| # | Repo · package | Files | Work |
|---|---|---|---|
| 2.1 | root · core | `ports/debug_access.py`, `ports/resource_lease.py` (new) | Protocols + `ResourceBusyError`. |
| 2.2 | root · core | `domain/target_profile.py`, `core/target_catalog.py`, `resources/targets/nordic.toml` (new); package data in `iotsploit-core/pyproject.toml` | nRF52840 and nRF5340 profiles from `_TARGETS`. nRF5340 lists only `app` until §7 Q1 is answered. `supports(name)`, `get(name)`. |
| 2.3 | root · core | `core/monitoring/arch/cortex_m.py` (new) | Move decoding, fault snapshot and recovery baseline out of `drv_jlink.py`; read via `DebugAccess`. Tests: `tests/test_arch_cortex_m.py` with a scripted register map, including DHCSR read-once. |
| 2.4 | root · drivers | `jlink/drv_jlink.py` | Slim to a pylink `DebugAccess`; `architectures() == {"cortex_m"}`. `core_status`/`fault_snapshot`/`recover_target` removed. Driver test becomes a transport test. |
| 2.5 | root · core | `core/monitoring/source.py`, `service.py`, `sources/mcu_core.py` (new) | `MonitorSource`, `SourceRegistry`, `MonitorService`, `McuCoreSource`. Config validation moves from `CoreMonitorSession.__init__` (same limits and messages). Tests: fake backend + fake lease — target rejection, arch mismatch, lease contention, cleanup when `open()` fails midway, cleanup on exception in `end()`. |
| 2.6 | root · core | `core/device_manager.py` | `get_driver_class(name)`; `get_driver_states()` adds `capabilities` (e.g. `["debug_access"]` from class metadata); constructor takes an optional `ResourceLeasePort`; `initialize_device` acquires it when the device declares a resource key. |
| 2.7 | root · django | `adapters/filelock/resource_lease.py` (new) | `FileResourceLease` per §2.6. Test: two subprocesses; second gets `ResourceBusyError` with holder; lock freed after the first is killed. |
| 2.8 | root · django | `composition_root/core_container.py` | Build `MonitorService` with registry (`mcu_core` → `McuCoreSource`), `DeviceDriverManager`, `TargetCatalog`, `FileResourceLease`; pass the lease to the manager. Test `tests/test_monitor_wiring.py`. |
| 2.9 | root · django | `tools/iot_protocol_runtime.py`, `iot_fuzzer/views_campaign.py`, `iot_fuzzer/urls.py` | Delete `CoreMonitorSession`, `_core_probe_owners`, `CoreProbeBusyError`. Runtime accepts `monitors` (and translates `core_monitor`); gets sources from the container and wraps each in its fuzzer monitor. `check_monitor(kind)` view + route; `mcu-core` alias. Update the two view tests to go through the container with a fake backend instead of patching the session. |
| 2.10 | ui · rust | `rust/src/api/jtag.rs`, `rust/Cargo.toml` | `jtag_open` acquires `usb:<vid>-<serial>/debug` per §2.6, `jtag_close` releases; busy → error naming the holder. Rust unit test for key normalisation shared via a test vector file with the Python test. |

Exit: J-Link + nRF52840 campaign on the rig; a boundary scan started during that campaign
on the same host is refused with a readable message, and vice versa; gate green in both repos.

### Phase 3 — New kinds and UI (one slice at a time, when a campaign needs it)

Each slice = detail type + port (if new) + adapter + source + policy + registry entry + tests.
Order by value/cost:

| Slice | Contents | Notes |
|---|---|---|
| 3.1 UART | `UartDetail`; `SerialLink`; pyserial adapter; `UartSource` (reader thread, ring buffer across windows, `late` flag); `UartLogMonitor` (crash regex → crash, banner → reset, heartbeat silence → hang) | If the resource equals the fuzz transport's port, the adapter taps `UARTInterface` RX instead of opening the port (§6 R3). |
| 3.2 Flutter | `test_controller.dart` sends `monitors`; `coreObservation` → `Map<String, MonitorObservation>`; `monitor_workspace.dart` renders one card per monitor by `kind`, generic JSON card for unknown kinds; target list from a catalog endpoint | Then remove the §3 legacy surfaces marked P3. |
| 3.3 Voltage | `PowerDetail`; `PowerSense`; SCPI adapter; `PowerSource`; `PowerMonitor` (brown-out, over-current, current collapse to sleep floor) | Blocked on instrument choice (§7 Q4). |
| 3.4 BLE | `BleDetail`; `BleObserver`; bleak adapter; `BleSource`; `BleLivenessMonitor` | Ubertooth driver stays for sniffing. |
| 3.5 Concurrency | `MonitorSetHarness` runs point-source `end()` concurrently across distinct resources | Only when a campaign has ≥ 2 point sources. |
| 3.6 Debug backends / archs | pyOCD or OpenOCD `DebugAccess`; `arch/riscv.py`, `arch/xtensa.py` | Only with hardware on the bench. |
| 3.7 nRF5340 net core | Add `net` to the profile; one `McuCoreMonitor` per core | Only after §7 Q1 proves multi-core access. |

## 5. Verification

- **Python gate, every root commit:** `tools/testing/test-python-full.sh`
  (`.agents/standards/testing.md`). Report pass/fail/skip/warning counts. No skipped or
  weakened unrelated tests.
- **Flutter, every ui commit:** `fvm flutter test` and `fvm flutter analyze`; format with
  `~/fvm/versions/3.35.7/bin/dart format` (the `.fvm` symlink is stale).
- **Rust, ui commits touching `rust/`:** `cargo test` in `ui/rust`.
- **Hardware, end of P1 and P2:** rig 10.8.0.14 (nRF52840 + J-Link). Manual check;
  10-case campaign with a known crashing payload; expected-reset payload; busy-probe 409;
  P2 adds the boundary-scan cross-lock check. Beware the rig's J-Link firmware
  auto-update trap (skip JLinkExe update prompts).
- **UI change in P3.2:** render the monitor workspace before/after to PNG and compare
  before calling it done.

## 6. Risks and controls

| # | Risk | Control |
|---|---|---|
| R1 | Legacy payload drifts and silently breaks the current Flutter build or history continuity | Phase 0 fixtures + one `legacy_core_observation` function + characterisation test |
| R2 | Shared driver instance (`get_driver_instance()` is one per plugin; pylink state on `self.jlink`) | Sources only use `get_driver_class()`; test that two sources get distinct instances |
| R3 | UART monitor and UART fuzz transport fight over one port | Same-resource detection in the plan validator; tap the transport reader instead of opening |
| R4 | Window edges: crash print / brown-out lands after `end()` | Per-source `settle_ms`, harness waits for the max; ring buffer overlaps windows; late data flagged on the previous case |
| R5 | Verdict conflicts across monitors | Fixed severity order, `decisive` flag, unanimous expected-reset rule; tests in 1.6 |
| R6 | DHCSR read-to-clear lost by an extra read | Only `arch/cortex_m.py` reads it; test counts reads per sample |
| R7 | Unbounded `detail` floods WebSocket/history | Caps in §2.1; artifact paths for full captures; test asserts size bound |
| R8 | File lock semantics differ between Python and Rust on Windows (`msvcrt.locking` byte-range vs `LockFileEx`) | Cross-language lock test on the Windows VM before P2 exit; if incompatible, both sides lock byte 0 explicitly |
| R9 | Multi-core over one pylink connection may not work | nRF5340 ships single-core in profiles until §7 Q1 is proven |
| R10 | Per-case latency grows with monitors | Window sources are cheap; P3.5 concurrency for point sources |

## 7. Open questions

| # | Question | Blocks | How to answer |
|---|---|---|---|
| Q1 | Is there an nRF5340 bench, and can one pylink connection read the net core (AHB-AP 1) while connected as `NRF5340_XXAA_APP`? | 3.7 | Bench spike: `coresight_read` with AP select |
| Q2 | ~~Does probe-rs `serial_number` for a J-Link equal pylink's serial after normalisation?~~ **Answered:** the rig probe's USB iSerial is `001050298903`, pylink reports `1050298903`; dropping leading zeros makes them equal. | 2.10 | Done |
| Q3 | Should the lock also cover the terminal page / ESP32 driver serial opens? | 3.1 | Decide when the UART slice starts; `initialize_device` covers drivers already |
| Q4 | Which instrument measures voltage/current (SCPI PSU, DMM, own board)? | 3.3 | Hardware decision |
| Q5 | Does the campaign UI need live per-monitor streaming, or per-case updates only? | 3.2 | UX decision |

## 8. Definition of done

- **P1:** `JtagHarness` gone; `MonitorSetHarness` + `McuCoreMonitor` in use; envelope
  emitted; legacy payload byte-identical in shape to Phase 0 fixtures; `MCUMonitor`
  deleted; gate green; rig check passed.
- **P2:** `CoreMonitorSession` and `_core_probe_owners` gone; no `import` of
  `iotsploit_drivers` in `iotsploit-core` or in `MonitorService` callers; nRF targets are
  data; `FileResourceLease` taken by Python and Rust; generic check endpoint live; gate
  green in both repos; rig + cross-lock check passed.
- **P3 slice:** kind's detail, source, policy and adapter merged with tests; appears in
  the Flutter workspace (generic card acceptable); no edits to `MonitorSetHarness`,
  `MonitorService`, the lease, or the recorder.

## 9. Out of scope

- Porting boundary scan to Python.
- `BaseMonitor`, `BoundaryMonitor`, `LinuxMonitor`/`Pi_Mgr`/`SystemMonitor`.
- Cross-host locking (probe on a remote Pi and boundary scan on a desktop cannot collide).
- Replacing pylink.

## 10. As built (2026-09-30)

### 10.1 Differences from the text above

| Plan said | Built | Why |
|---|---|---|
| Profiles in `resources/targets/nordic.toml`, catalog in `core/target_catalog.py` | `core/monitoring/targets/nordic.json`, `core/monitoring/catalog.py` | Python 3.10 (dev machines) has no `tomllib`; no new dependency. |
| `sources/…` under `core/monitoring/`, arch under `core/monitoring/arch/` | Same, plus `core/monitoring/__init__.py` exporting the public names | — |
| `DebugAccess` methods take a core | No core parameter; one connection = one core | nRF5340 net-core access is unproven (Q1). Add the parameter with the first multi-core backend. |
| `DebugAccess` names `read_reg` / `halt` / `resume` / `reset` | `read_registers(names)`, `halt`, `is_halted`, `resume`, `reset_core`, plus `attach`/`detach`, `debug_architectures` | `reset`/`close` clash with `BaseDeviceDriver`; attach keeps probe-specific device attributes out of core. |
| `TargetMonitor.recover(expected)` | Not in the protocol; each policy recovers inside `after()` | Recovery budgets are per-kind policy; the harness never needed to drive it. Added `preflight()` and `kind` instead. |
| Verdicts `ok · crash · hang · expected_reset` | Plus `inconclusive` (stop for inspection, not a crash) | `JtagHarness` already stopped on unconfirmed faults, halts and unavailability without calling them crashes. |
| `HarnessResult.core_observation` kept as a property | Replaced by `monitor_verdicts`; event `CORE_STATUS` → `MONITOR_STATUS` | Only the fuzzer used it; Django re-adds the flat `core_observation` for clients (§3). |
| Lock directory `$XDG_RUNTIME_DIR/…` on Linux | `/tmp/iotsploit-<uid>/locks` on Linux and macOS; `IOTSPLOIT_LOCK_DIR` overrides | Must not depend on per-process environment: daphne and the Flutter app may see different `XDG_RUNTIME_DIR`. |
| Rust lock in `rust/src/api/jtag.rs` | `rust/src/probe_lock.rs` (private module), taken in `jtag.rs` `open`, released when the session drops | Keeps it out of the flutter_rust_bridge API: no codegen change. |
| Separate `test_monitor_service.py` / `test_arch_cortex_m.py` / `test_monitor_wiring.py` | `iotsploit-core/tests/test_target_monitoring.py`, `test_device_manager_lease.py`; `iotsploit-django/tests/test_target_monitor_runtime.py` | Same coverage, fewer files. |
| — | `BaseDeviceDriver.resource_key(device)` (default None); J-Link returns its `usb:…/debug` key | How the device manager learns what to lease without knowing drivers. |

### 10.2 Verification performed

- **Python gate:** `tools/testing/test-python-full.sh` — baseline 1814 passed / 5 skipped;
  after the change 1889 passed / 5 skipped; Ruff clean.
- **Rust:** `cargo test --lib` in `ui/rust` — 44 passed, 1 ignored (manual interop test);
  `rustfmt --check` clean on touched files.
- **Cross-runtime lock (Linux):** a Python process holding `usb:1366-1050298903/debug`
  made the Rust `ProbeLock::acquire` fail with the Python holder named
  (`interop_refuses_a_lock_held_by_the_python_backend`, run with `--ignored`).
- **Rig 10.8.0.14, nRF52840-DK, J-Link 1050298903, new code run from a copy of the tree
  (the rig checkout and running daphne were not touched):**
  - Legacy `core_monitor` UART campaign (VCOM `/dev/ttyACM0`): flat `core_observation`
    keys identical to the Phase 0 capture for preflight, per case and `before`.
  - `monitors` plan campaign: same, with `monitor_verdicts` alongside.
  - Real fault: core forced to fetch from `0x30000000` mid-campaign → verdict `crash`,
    "Persistent fault exception observed: instruction bus error, escalated configurable
    fault"; snapshot stacked PC `0x30000000`; `reset_continue` recovered in 94 ms; campaign
    completed the remaining cases.
  - Manual check (legacy body and plan-entry body): 200. From a second process during a
    campaign: 409 "…in use by campaign … (iotsploit-python, pid …)". After it: 200.

### 10.3 Not yet verified

- Windows lock interop (R8): Python `msvcrt.locking` byte 0 vs Rust `File::try_lock`.
  Needs the Windows VM.
- The Flutter app on the rig taking the Rust lock against a live campaign (only the
  module-level interop test ran; the app was not rebuilt).
- Device-manager leasing through the real Devices page (unit-tested only).
- Rig operators need the `uucp` group (or equivalent) for VCOM campaigns; the test used a
  temporary ACL that was removed afterwards.

