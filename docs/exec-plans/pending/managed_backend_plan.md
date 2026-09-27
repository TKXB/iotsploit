# Managed Backend Plan

## Status

- **State:** Phase 1 implemented on `feat/backend-status` in both repos
  (2026-09-27), not yet committed. Phase 2 is ready to start. Phase 3 is gated
  (see [Phase 3 gate](#phase-3-gate))
- **Draft date:** 2026-09-27
- **Decision owner:** User
- **Repos touched:** this repo (Python) and `ui/` (Flutter, its own git repo)
- **Depends on:** [`../active/redis_optional_dual_runtime_plan.md`](../active/redis_optional_dual_runtime_plan.md),
  which provides `IOTSPLOIT_RUNTIME=local`. Its hardware acceptance is still pending
- **Visual summary:** https://claude.ai/artifact/3MG8jBg7pwE1j6QFVAR2pP

**Goal.** Let the desktop app start and own its Python backend, the way KiCad
owns its Python process, and keep today's option of connecting to a remote rig.
Every build gets one live backend status.

## Decisions

| Question | Decision |
|---|---|
| Local mode, Remote mode, or both | Both. Remote stays exactly as it is today |
| Runtime used by Local mode | `IOTSPLOIT_RUNTIME=local` (no Redis, no Celery broker) |
| Build that gets Local mode | prod release, desktop only (Windows, Linux, macOS). Also dev desktop, for development |
| Bundle Python in prod | Yes, but only after the Phase 3 gate is met |

Android and Web can't run a Python process, so they stay Remote-only. The
offline (Toolkit) flavor doesn't change.

## Governing Standards

- `AGENTS.md`: Delete > Replace > Add, and solve at the owner. Local mode reuses
  the existing `iotsploit --runserver` launcher instead of building a second
  one. The dead Terminal Startup Command setting is replaced, not kept beside
  the new one.
- `docs/architecture.md`: the health view is a Django adapter concern. Core
  doesn't learn about it.
- `ui/AGENTS.md`: the status bar and the details panel reuse components from
  `lib/screens/component_showcase/component_showcase_page.dart`.

## Current State

- **The UI and the backend are only linked by two URLs.** `ConfigProvider`
  (`ui/lib/providers/config_provider.dart`) holds `apiBaseUrl` and `wsBaseUrl`,
  with defaults `http://0.0.0.0:8888` and `ws://0.0.0.0:9999`. The user types
  them in, or finds a rig with UDP discovery on port 37020
  (`ui/lib/services/server_discovery_service.dart` ↔
  `iotsploit_django/tools/discovery_server.py`).
- **The app can't see backend status.** Nothing in the UI reports whether the
  backend is up. Screens just fail their own requests. The only status report
  is the CLI's `service status` (`resource_commands.py`), and it only covers
  processes started by that CLI session.
- **Headless start already exists.** `iotsploit --runserver`
  (`iotsploit_cli/console.py` `main()`) starts daphne and the MCP bridge
  (`django_commands.py` `_start_services`), then waits. It already takes
  `--host`, `--api-port`, `--ws-port`, `--mcp-host` and `--mcp-port`, and it
  cleans up on SIGTERM, SIGINT, SIGHUP and at exit.
- **Clean shutdown needs signals.** On Windows, `Process.kill` from Dart ends
  only the parent, so its child processes keep running and keep their ports.
  A parent that crashes sends no signal at all.
- **Some data paths are fixed and some can be configured:**
  - The database is configurable through `IOTSPLOIT_DATABASE_PATH`
    (`settings/base.py`).
  - Service logs are configurable through `IOTSPLOIT_SERVICE_LOG_DIR` or
    `IOTSPLOIT_RUNTIME_DIR`, and default to the temp dir.
  - Uploads can't be moved: they're fixed at `settings.BASE_DIR / "uploads"`
    (`view_handlers/file_views.py`). In an installed or bundled package that
    folder is inside the install and may be read-only.
  - `Report_Mgr` writes `sat_logs` relative to a root directory. Phase 3 must
    check where that root ends up in a bundle.
- **The Terminal Startup Command setting is dead.** It's hard-coded to
  `cd /home/tkxb/... && poetry shell && python3 console.py`, and nothing reads
  it except the Settings field that edits it. `Config.getTerminalStartupCommand`
  has no callers.

## Design

### One owner in Flutter

`BackendProvider` (new, `ui/lib/providers/backend_provider.dart`, registered
next to `ConfigProvider` in `bootstrap.dart`) owns three things:

1. **Mode:** `local` or `remote`, persisted in SharedPreferences. It defaults to
   `local` on prod desktop once Phase 3 ships, and to `remote` everywhere until
   then.
2. **Process** (Local mode only): spawning, the stdout/stderr ring buffer
   (last ~500 lines), start, stop and restart, and the exit code.
3. **Health poll** (both modes): `GET /api/health/` every 5 s with a 2 s
   timeout. The result is combined with the process state into one status.

In Local mode, `ConfigProvider` takes the local URLs in memory only. The saved
Remote URLs aren't overwritten, so switching back to Remote returns to the rig
the user had.

### Status states

| State | Meaning | Modes |
|---|---|---|
| `checking` | No answer yet from the configured server, at startup or after the address changes | Both |
| `stopped` | The local backend isn't running | Local |
| `starting` | The process was spawned and health isn't green yet. Times out after 30 s | Local |
| `online` | Health answered and every check passed | Both |
| `degraded` | Health answered and a check failed | Both |
| `versionMismatch` | Backend `api_version` ≠ the app's expected `api_version`, or the server returns 404 because it predates `/api/health/` | Both |
| `unreachable` | No health answer from the remote URL | Remote |
| `crashed` | The process exited. Keeps the exit code and the log tail | Local |

### Health endpoint

`GET /api/health/` goes in `iotsploit_django/web/api/misc_urls.py`, with the view
in `web/views.py` next to `set_log_level`.

```json
{
  "version": "0.0.19",
  "api_version": 1,
  "runtime": "local",
  "checks": { "database": "ok" }
}
```

- `version` is the installed `iotsploit-django` package version.
- `api_version` is an integer constant in Python, with a matching constant in
  `BackendProvider`. Bump it when a change breaks the UI↔Python contract. This
  is the first cheap guard on the contract gap: the UI calls 48 endpoints and
  16 have tests.
- `checks.database` uses `connection.ensure_connection()`. In `distributed`
  runtime, add `checks.redis` from the existing Redis check. Don't call Celery
  inspect, because it's too slow to poll.
- Always return 200 while the process is up. A failed check shows as a value
  other than `"ok"`, and Flutter maps that to `degraded`.

### Local mode startup

1. Pick three free loopback ports (bind `ServerSocket` to port 0, read the port,
   close). This avoids 8888/9999, which a rig tunnel or a second copy of the
   app may already use.
2. Spawn `<backend executable> --runserver --exit-with-parent --host 127.0.0.1
   --api-port A --ws-port B --mcp-host 127.0.0.1 --mcp-port C`, with
   `IOTSPLOIT_RUNTIME=local` and `IOTSPLOIT_DATABASE_PATH=<app-data>/iotsploit.db`.
3. Stream stdout and stderr into the ring buffer. State is `starting`.
4. Poll health until it's green. Then hand the URLs to `ConfigProvider`.
   State is `online`.
5. When the app quits or crashes, the OS closes the child's stdin. The backend
   sees EOF, runs its existing `_shutdown()`, and exits.

If a port was taken during the race between steps 1 and 2, the process exits
with a bind error and shows `crashed` with the log. The user clicks Restart,
which picks new ports. We won't build a retry loop.

### `--exit-with-parent`

This is a new flag in `console.py` `main()`, used only with `--runserver`. When
it's set, a daemon thread blocks on `sys.stdin.read()`. On EOF it calls the
existing `_shutdown()` and then `os._exit(0)`. It works the same way on all
three operating systems and needs no signals.

## Phases

### Phase 1: Backend status (small, both modes)

Python:
- Add the health view and route.
- Add one Django test-client test for the view, since the UI now depends on
  that contract.

Flutter:
- `BackendProvider` with the health poll and the states that apply to Remote
  mode (`online`, `degraded`, `versionMismatch`, `unreachable`).
- **A backend status bar at the bottom of the side menu.** It takes over the
  footer slot (`_buildFooter()` in `lib/screens/main/components/side_menu.dart`),
  which today holds only the Discord button. It spans the full drawer width and
  shows a colored state dot, "Backend" and the state label. A second line shows
  the mode and the version or host, for example `Remote · 10.8.0.10` or
  `Local · 0.0.19`. Tapping it opens a details panel with the URL, version,
  runtime and failing checks. The bar appears only when
  `activeFlavor.enableRemoteApi` is true (prod and dev). In offline and jtag the
  footer is empty. It works the same in the mobile drawer.
- **Move Discord into Settings.** Add a Discord row to the About card in
  `lib/screens/settings/settings_page.dart`, under Version, Build, Released and
  Platform. It uses the existing `brandDiscord` color and
  `assets/icons/discord.svg`, with an open-in-new icon on the right. Its link
  opens the same way as `_openPrivacyPolicy`, including the snackbar when the
  link fails, replacing the side menu's `debugPrint`-only error handling. Delete
  `_launchDiscord` and the `url_launcher` import from `side_menu.dart`. Settings
  is enabled in every flavor, so Discord stays reachable everywhere, including
  offline and jtag.

**Done when:** stopping a remote backend shows `unreachable` within one poll,
and starting it again shows `online`. A backend with a different `api_version`
shows `versionMismatch`. The Discord row in Settings → About opens the invite
link, and the offline flavor's side menu shows no status bar.

### Phase 2: Managed Local backend (medium, desktop)

Python:
- `--exit-with-parent`.

Flutter:
- The mode setting (Local or Remote) in `lib/screens/settings/settings_page.dart`.
- **Replace** the Terminal Startup Command field with a Backend Executable field.
  It defaults to `iotsploit` on PATH, and a Poetry venv path can be entered
  (`.../bin/iotsploit`). Delete `_terminalStartupCommand`, its setter and
  persistence, and `Config.getTerminalStartupCommand`.
- The launcher in `BackendProvider`: ports, spawn, log buffer, start, stop and
  restart, plus the `stopped`, `starting` and `crashed` states.
- The details panel adds Start, Stop and Restart buttons and the log tail.
  Local mode is desktop only. The setting is hidden on Android and Web.

**Done when:** on a dev Linux build, the app starts, stops and restarts its
backend. After `kill -9` of the app, `pgrep -f iotsploit` finds nothing, and the
same check passes on Windows (Task Manager).

### Phase 3: Bundle Python in prod desktop releases (large, gated)

- Preparation: make uploads follow an env var (`IOTSPLOIT_UPLOAD_DIR`, next to
  `IOTSPLOIT_DATABASE_PATH`), and make sure `Report_Mgr`'s `sat_logs` root
  resolves to a writable folder.
- CI builds a relocatable CPython (python-build-standalone) on each OS and
  installs the IoTSploit wheels into `backend/`. Native wheels can't be
  cross-built.
- Package `backend/` in the AppImage (`ui/linux-appimage/AppImageBuilder.yml`),
  the Windows installer and the macOS `.app`. Sign and notarize the embedded
  binaries and `.so` files on macOS.
- The prod desktop build defaults to Local mode and uses the bundled executable.
  A bundled backend always matches the app version, so Local mode can't have a
  version mismatch.

**Done when:** a clean VM on each OS, with no Python installed, runs the prod
release and reaches `online` on first launch.

#### Phase 3 gate

Start Phase 3 only when both are true:

1. **Local runtime has passed hardware acceptance** in
   `redis_optional_dual_runtime_plan.md`. Bundling it would put an unvalidated
   runtime in front of every prod user.
2. **There is evidence prod desktop users need the Python backend without a
   rig.** Most hardware work already runs in Rust inside the app (JTAG, USBTMC,
   SSH, flashing), and the MCP server lives on the rig. If most users have a
   rig, Phase 3 mainly makes the installer bigger.

Measure the bundle size and list the native-library dependencies (libusb, pcap
and so on) before committing to dates.

## Risks

| Risk | Mitigation |
|---|---|
| Orphaned daphne or MCP processes hold ports after a crash | `--exit-with-parent` on stdin EOF, which doesn't rely on signals |
| Port race between choosing a port and binding it | Shows `crashed` with the log. Restart picks new ports |
| Read-only install folders (bundles) | DB via `IOTSPLOIT_DATABASE_PATH`. Uploads and `sat_logs` fixed in Phase 3 preparation |
| Installer size | Measured at the start of Phase 3. Trim unused extras |
| Native libraries missing on clean machines | List them from the wheel build and test on a clean VM per OS |
| macOS Gatekeeper blocks embedded Python | Add it to the existing signing and notarization step |
| USB or raw-socket permissions | The backend runs as the desktop user. Reuse the app's existing udev and driver guidance |

## Out of Scope

- An embedded Python console like KiCad's scripting console. The CLI already
  covers that need.
- Local mode on Android, iOS or Web.
- `distributed` runtime in Local mode.
- Changing UDP discovery or any other part of Remote mode.

## Validation

- Python: `tools/testing/test-python-full.sh`.
- Flutter (from `ui/`): `tools/testing/test-flutter-full.sh`.
- Manual: each phase's **Done when** check, run on a real build.
