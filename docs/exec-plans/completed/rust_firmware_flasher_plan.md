# Rust Lightweight Firmware Flasher — Plan

_Drafted: 2026-06-27_

A standalone Rust firmware-flasher manager that flashes ESP32, FPGA, and
J-Link/SWD targets, independent of the Python project, and integrates into the
existing Flutter app (`ui/`) over `flutter_rust_bridge`.

## Goals & constraints

- **Lightweight**: minimal runtime deps, no Python interpreter, fast startup.
- **Backends**: ESP32 (esptool-equivalent), FPGA flasher, J-Link.
- **Separate from Python**: own Cargo workspace, no dependency on
  `iotsploit-*` packages. Manifest format stays JSON-compatible so the same
  firmware definitions work in both worlds.
- **Flutter-ready**: exposes a clean async API with progress streaming, consumed
  through the FRB pipeline that already exists in `ui/`.

## Existing context that shapes the design

- Flutter app at `ui/`, FRB `2.11.1`, Rust crate `rust_lib_admin` at `ui/rust/`.
- That crate already depends on `nusb`, `tokio`, `tracing`, `anyhow`, `once_cell`
  — reuse these; no new USB/async stack needed.
- Current Python manifest format (`conf/firmware_manifest.json`):
  `{ "<name>": { "path", "device_type", "version", "flash_options{...}" } }`.
  Keep this schema verbatim for drop-in compatibility.
- Desktop Linux x64 is the proven build target (existing `build/linux/x64`).
  Treat desktop as primary; mobile USB flashing is a stretch goal (see Risks).

## Key decision: native Rust backends vs. subprocess wrappers

The brief says "use esptool, fpga flasher and jlink." There are two ways to do
that. **Recommendation: hybrid — native where mature crates exist, subprocess
only for FPGA.**

| Target | Recommended backend | Why |
|---|---|---|
| ESP32 | **`espflash`** crate (native Rust) | Pure-Rust esptool replacement; flash/erase/monitor, progress callbacks. Removes the Python+esptool dependency entirely. |
| J-Link / SWD (nRF52, STM32) | **`probe-rs`** crate (native Rust) | Natively drives J-Link, ST-Link, CMSIS-DAP. Flashes ELF/hex/bin. No JLinkExe / OpenOCD needed. |
| FPGA (ECP5/Lattice via FT2232) | **`openFPGALoader`** subprocess | No mature pure-Rust loader; shell out to the existing binary with `--cable`/`--board`. |

This gives a near-zero-install path for the two most common cases and isolates
the only external-binary dependency to FPGA. A `subprocess` fallback backend
(calling `esptool` / `JLinkExe`) can be added behind the same trait if a board
needs it, but should not be the default.

> Open question to confirm before Phase 1: are you OK depending on `espflash` +
> `probe-rs` (native), or do you specifically need to call the vendor CLIs
> (`esptool`, `JLinkExe`, `openFPGALoader`) for all three? This changes Phases
> 1–2 substantially.

## Proposed architecture

**Location (decided 2026-06-28):** all-in-one **inside the Flutter app** at
`ui/firmware/` — a self-contained Cargo workspace (no `iotsploit-*` coupling)
that `ui/rust` consumes via a relative path dep. Still independently
buildable/testable with plain `cargo`.

```
ui/
  rust/                      # existing FRB crate `rust_lib_admin`
  firmware/                  # NEW self-contained workspace
    Cargo.toml               # [workspace]
    crates/
      firmware-core/         # backend-neutral core — no espflash/probe-rs dep
        image.rs             # FlashImage, FlashOutcome (neutral primitives)
        progress.rs          # FlashProgress events (incl. Verifying / Done{skipped})
        error.rs             # FlasherError (thiserror)
        manifest.rs          # OPTIONAL (`manifest` feature): JSON -> neutral ManifestEntry
      firmware-esp32/        # espflash backend (Phase 1)
      firmware-probe/        # probe-rs backend, J-Link/SWD (Phase 2)
      firmware-fpga/         # openFPGALoader subprocess backend (Phase 3)
      cli/                   # standalone CLI for testing without Flutter
```

Backends are independent crates; the Flutter FRB layer (`ui/rust`) depends on
the ones it needs and routes by `device_type`. Each backend owns its own
device-specific options/enums (e.g. `Esp32FlashJob` in `firmware-esp32`) so
`firmware-core` stays neutral and never pulls in a flashing library. There is no
Python `FirmwareToolService` equivalent — the catalog lives in Flutter (presets
+ file picker), not in Rust.

### Core trait

```rust
#[async_trait]
pub trait FlashBackend: Send + Sync {
    fn supports(&self, device_type: &str) -> bool;
    fn is_available(&self) -> BackendAvailability;       // native=always; fpga=which(openFPGALoader)
    async fn flash(&self, job: &FlashJob, progress: ProgressSink) -> Result<FlashOutcome>;
    async fn erase(&self, target: &FlashTarget, progress: ProgressSink) -> Result<()>;
    async fn info(&self, target: &FlashTarget) -> Result<DeviceInfo>;
}
```

`ProgressSink` is generic in core; in the Flutter layer it is backed by an FRB
`StreamSink<FlashProgress>` so the UI gets a live progress bar.

## Flutter integration

Reuse the existing bridge — do **not** stand up a second FRB pipeline.

1. Add the flasher crates as **relative path dependencies** of `ui/rust`
   (`rust_lib_admin`), e.g. `firmware-esp32 = { path = "../firmware/crates/firmware-esp32" }`.
   Keep `ui/firmware/` its own workspace so it still builds/tests on its own.
2. Add `ui/rust/src/api/firmware_flasher.rs` exposing the FRB surface:

The FRB surface is **flash-centric** — Dart owns the firmware catalog (presets +
file picker), so there is no `list/add/remove` over the bridge:

```rust
pub fn detect_devices() -> Vec<DetectedDevice>;
pub fn backend_status() -> Vec<BackendStatus>;          // which flashers usable on this host
pub fn device_info(opts: Esp32FlashOptionsDto) -> Result<DeviceInfo>;
pub async fn flash_firmware(
    job: Esp32FlashJobDto,                               // [{address, path}] + options, built by Dart
    sink: StreamSink<FlashProgress>,                     // streamed progress
) -> Result<FlashOutcome>;
pub async fn erase_firmware(opts: Esp32FlashOptionsDto, sink: StreamSink<FlashProgress>) -> Result<()>;
```

3. Regenerate bindings (`flutter_rust_bridge_codegen generate`), then build a
   thin Dart `FirmwareFlasherService` + a flash screen (preset/file picker →
   device picker → progress bar) in the Flutter app.

Firmware catalog: **Dart owns it** — bundled preset binaries + a
`firmware_presets.json` shipped as Flutter assets, plus a file picker for custom
`.bin`s. Dart materializes any asset to a real temp path and passes concrete
`(address, path)` images to Rust. No Python, no shared `~/.iotsploit` manifest.

## Dependencies (flasher crates)

| Crate | Use |
|---|---|
| `espflash` | ESP32 flashing |
| `probe-rs` | J-Link/SWD flashing |
| `serialport` | serial port enumeration / ESP32 port selection |
| `nusb` | USB device detection (already in `ui/rust`) |
| `tokio` | async runtime (already present) |
| `serde` / `serde_json` | manifest parsing |
| `thiserror` / `anyhow` | errors |
| `tracing` | logging (already present) |
| `which` | locate `openFPGALoader` for the FPGA backend |

## Status (2026-06-28)

- **Backend decision resolved:** native crates — `espflash` (ESP32) + `probe-rs`
  (J-Link/SWD), FPGA via `openFPGALoader` subprocess.
- **Phases 0–1 implemented and verified** under `ui/firmware/` (workspace builds,
  7 unit/integration tests pass, CLI parses the real 17-entry manifest and the
  `info` path enumerates ports cleanly). The crate is named `firmware-core` (the
  "flasher-core" naming earlier in this doc is the same crate). espflash version
  pinned to **4.4**. Key API facts captured during Phase 1:
  - Flash flow: `serialport::new(..).open_native()` → `Connection::new(..)` →
    `Flasher::connect(conn, use_stub, verify, skip, chip, baud)` →
    `write_bin_to_flash(addr, &data, &mut ProgressCallbacks)` / `erase_flash()` /
    `device_info()`. All synchronous — the async backend runs it on
    `spawn_blocking`.
  - **Progress is reported in flash *chunks*, not bytes** (`init(addr, num_chunks)`,
    `update(chunk_idx)`), so `FlashProgress::ImageProgress` is a fraction; byte
    totals come from `FlashOutcome`.
  - espflash is built with `default-features = false, features = ["serialport"]`
    (no `cli`/clap).
- **Next:** Phase 2 (probe-rs) / Phase 5 (Flutter bridge) — not yet started.

## Phased delivery

- **Phase 0 — Scaffold core.** ✅ _Done._ Workspace, `firmware-core` types, JSON-compatible
  manifest loader (built-in + user merge), `FlashBackend` trait, progress model,
  errors. Unit tests against the existing manifest fixture. _No hardware._
- **Phase 1 — ESP32 backend (`espflash`).** ✅ _Done._ flash (single + multi-file),
  erase, chip info, progress events, port auto-select. Validated via the
  standalone `cli` crate (`firmware-flasher`). Live-hardware flash deferred to a
  user-authorized run (devices are connected but flashing is destructive).
- **Phase 2 — Probe backend (`probe-rs`).** J-Link/SWD flash for `nrf52` /
  `stm32f4` entries (hex/bin/elf), erase, chip info, progress.
- **Phase 3 — FPGA backend.** `openFPGALoader` subprocess; map `flash_options`
  (`cable`, `board`, `target=sram|flash`, `external_flash`) to args; parse
  stdout for coarse progress; `is_available` via `which`.
- **Phase 4 — Device detection.** `nusb` + `serialport` enumeration; map
  VID/PID to likely `device_type`; expose `detect_devices()`.
- **Phase 5 — Flutter bridge + rewrite the UI firmware tab (Rust-only).**
  `api/firmware_flasher.rs`, regen bindings, new Dart `FirmwareFlasherService`,
  and rebuild the **Utils → Firmware** tab to run entirely on Flutter + Rust:
  preset list (bundled assets) + file picker, ESP32 flash/erase over FRB with
  streamed progress, **no Python/Django calls**. See "Phase 5 detail" below.
- **Phase 6 — Packaging & docs.** Asset bundling, backend availability checks,
  README, and a desktop end-to-end flash test.

A standalone `flasher-core` + `flasher-esp32` + CLI example (Phases 0–1) is the
minimal first milestone that proves the approach end-to-end without Flutter.

## Phase 5 detail — migrating the UI firmware tab to Rust

### Current state (HTTP → Django → Python)

- `ui/lib/screens/utils/utils_page.dart` — the **Firmware** tab; loads the list,
  add/info dialogs, flash/erase actions.
- `ui/lib/services/firmware_service.dart` — HTTP client to Django
  `/api/firmware/*`: `getFirmwareList`, `getFirmwareInfo`, `addFirmware`,
  `removeFirmware`, `flashFirmware`, `downloadFirmware`, `eraseFirmware`.
- `ui/lib/models/firmware.dart` — `Firmware`, `FirmwareResponse`.

Every operation, including the actual flash, round-trips to the Python backend.

### Target — Flutter + Rust only, no Python in the flash path

**Decided (2026-06-28):** the Firmware tab does **not** call the Python/Django
backend for flashing at all. Everything firmware-related is Flutter + Rust (FRB).
Django's `/api/firmware/*` is dropped from this tab.

Firmware selection is **both** a built-in preset list **and** a file picker:
- **Presets** — a small set of known firmware bundled with the app as Flutter
  **assets** (binaries + a local `firmware_presets.json` listing name,
  device_type, and the `(address, asset)` images). Read by Dart; no Python, no
  network. This recreates today's named-list UX.
- **File picker** — the user picks an arbitrary `.bin` (and address, or uses the
  ESP defaults) to flash ad-hoc.

| UI action | Phase 5 home | Notes |
|---|---|---|
| Firmware list | **Flutter (assets)** | From bundled `firmware_presets.json`; no catalog server. |
| Pick custom file | **Flutter file picker** | `file_picker` plugin → a real path. |
| Flash (esp32) | **Rust FRB** | Streamed progress, native. |
| Erase (esp32) | **Rust FRB** | |
| Device chip info / detect | **Rust FRB** | `info()` / `detect_devices()`. |
| Flash/erase (fpga, nrf, stm32) | **Unavailable (disabled)** | No Python fallback; enabled when Phases 2–3 land those Rust backends. |
| Add / remove preset | **Flutter (local)** | Optional: edit a user preset file in app-support dir. |
| Download from URL | **Deferred / Rust later** | Optional; can be a Rust `reqwest` helper later, not Python. |

### Image paths — assets must become real files

Rust/espflash needs a **real filesystem path**. Preset binaries shipped as
Flutter assets are not guaranteed to be plain on-disk files at runtime, so:

1. Dart loads the preset's asset bytes and writes them to a **temp/cache file**
   (`path_provider` temp dir), getting a concrete path.
2. Dart builds the `Esp32FlashJob`-equivalent (`[{address, path}]` + options)
   and calls Rust FRB `flash_firmware(job, sink)`.
3. For the file-picker case the path is already real — pass it straight through.
4. Rust flashes locally with espflash and streams `FlashProgress` back.

No `resource:`/`importlib` concerns here — that was a Python packaging concept,
and Python is out of this path entirely. (The optional Rust `manifest` feature
from Phase 1 is **not** needed for the UI; Dart owns preset parsing.)

### Device-type scope

Phase 5 ships **ESP32 only** (Phase 1). FPGA / nRF / STM32 entries appear in the
UI but their flash/erase actions are **disabled with an "not yet supported"
note** — they are *not* routed to Python. They light up when Phases 2–3 add the
probe-rs and FPGA backends and their FRB surface.

### Dart-side changes

- **New** `ui/lib/services/firmware_flasher_service.dart` wrapping the generated
  FRB bindings (`flashFirmware`, `eraseFirmware`, `detectDevices`,
  `backendStatus`). Exposes flash as a **`Stream<FlashProgress>`**, not a
  `Future<bool>`.
- **New** `ui/lib/models/flash_progress.dart` mirroring the Rust `FlashProgress`
  enum (connecting / chip-detected / image-progress / verifying / done / finished).
- **New** preset assets: `ui/assets/firmware/…` binaries +
  `firmware_presets.json`, registered in `pubspec.yaml`; a small Dart loader.
- **New** dependency on a `file_picker` plugin (custom-file flow) and
  `path_provider` (temp path for asset → file).
- **Edit** `utils_page.dart`: replace `FirmwareService` HTTP calls with the
  preset loader + file picker + `FirmwareFlasherService`; add a live progress
  bar driven by the stream; disable flash for not-yet-supported device types.
- **Remove/retire** `firmware_service.dart` (HTTP) and the
  `Firmware`/`FirmwareResponse` models from this tab (delete once nothing else
  references them).

Net result: the Firmware tab runs entirely on Flutter + Rust; the Django
firmware endpoints can be removed from the app's dependency surface.

## Risks & open questions

- **Native vs. CLI backends** — confirm the key decision above before Phase 1.
- **Mobile flashing** — `espflash`/`probe-rs`/serial assume host USB access.
  Android needs the USB-host API via platform channels; iOS effectively can't.
  Recommend scoping v1 to **desktop (Linux/Windows/macOS)**, matching the
  current build target.
- **FPGA `openFPGALoader` must be installed** on the host — surfaced through
  `backend_status()` so the UI can warn instead of failing mid-flash.
- **probe-rs J-Link driver** — works with J-Link probes directly; verify your
  specific probe/target chip families are in probe-rs's supported list during
  Phase 2.
- **udev/permissions on Linux** — USB flashing needs udev rules / dialout group;
  document setup.
- **Repo placement** — _Decided (2026-06-28):_ all-in-one under `ui/firmware/`
  (self-contained workspace, relative path dep from `ui/rust`). Kept separate
  from `ui/rust` so cargokit/FRB build of `rust_lib_admin` is undisturbed.
- **No Python in the firmware tab** — _Decided (2026-06-28):_ the tab is Flutter
  + Rust only; Django `/api/firmware/*` is dropped from it. Firmware comes from
  bundled presets + a file picker (Dart-owned), not a catalog server.
- **UI flash is host-local** — _Decided:_ app and device are always on the same
  computer, so native flash always sees the device. Gate flash on
  `backendStatus()` only to cover "native lib missing / device type not yet
  supported" (FPGA/nRF/STM32 until Phases 2–3) — those are **disabled**, not
  routed anywhere else.
- **Asset → real path** — preset binaries ship as Flutter assets; Dart must copy
  them to a temp file (`path_provider`) before handing the path to Rust, since
  espflash needs a concrete on-disk path.
```
