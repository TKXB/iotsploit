# Backend Status Plan

## Status

- **State:** Completed 2026-09-27. Only Phase 1 shipped. The later phases were
  dropped (see [Dropped](#dropped))
- **Decision owner:** User
- **Commits:** `7d29c191` (this repo), `da528a9` (`ui/`), on `dev`

**Goal.** Let the app tell, on every page, whether its backend answers, which
version it runs, and whether its dependencies work. Before this, a dead or
mismatched backend showed up only as each screen failing its own request.

## What shipped

### Python: `GET /api/health/`

View `health` in `iotsploit_django/view_handlers/misc_legacy_views.py`, routed
in `web/api/misc_urls.py`, tested in `iotsploit-django/tests/test_health_endpoint.py`.

```json
{
  "version": "0.0.9",
  "api_version": 1,
  "runtime": "local",
  "checks": { "database": "ok" }
}
```

- `version` is the installed `iotsploit-django` package version.
- `api_version` is `API_VERSION`, an integer. **Bump it together with
  `expectedBackendApiVersion` in `ui/lib/providers/backend_provider.dart`**
  whenever a change breaks what the UI expects from the API.
- `checks.database` uses `connection.ensure_connection()`. In `distributed`
  runtime, `checks.redis` pings Redis with a 1 s timeout.
- The endpoint always returns 200 while the process is up. A failed check is a
  value other than `"ok"`.
- It's separate from `/api/system_health/`, which reports installed host tools
  and is too slow to poll.

### Flutter: status bar in the side menu

- `lib/providers/backend_provider.dart` polls `/api/health/` every 5 s with a
  2 s timeout and follows `ConfigProvider.apiBaseUrl`. A slow answer from a
  previous server can't overwrite the current one.
- `lib/screens/main/components/backend_status_bar.dart` is the side menu
  footer, shown in prod and dev (`activeFlavor.enableRemoteApi`). Tapping it
  opens a dialog with the server, version, API version, runtime, failing
  checks and the raw error, plus Server settings and Check now.
- The Discord button that used to sit in that footer moved to the Settings
  About card.

| State | Meaning |
|---|---|
| `checking` | No answer yet, at startup or after the address changes |
| `online` | Health answered and every check passed |
| `degraded` | Health answered and a check failed |
| `versionMismatch` | `api_version` differs from the app's, or 404 because the server predates `/api/health/` |
| `unreachable` | No answer, a non-200/404 status, or a body that isn't health JSON |

## Dropped

**Phase 2, the app starting its own backend.** A local backend is only a URL
that points at this computer, so a mode switch or a second URL pair adds
nothing. What remained was a Start button and cleanup on exit, which saves
typing `iotsploit --runserver` in a terminal the developer already has open.
That didn't justify process management in Dart, a new Python flag, and Windows
child-process handling.

**Phase 3, Python bundled in prod desktop releases.** It's the only case where
the app must launch the backend itself, because a prod user has no terminal
and no `iotsploit` command. It was gated on Local runtime passing hardware
acceptance (`active/redis_optional_dual_runtime_plan.md`) and on evidence that
prod desktop users need the Python backend without a rig. Neither was met.

If Phase 3 is ever wanted, it needs a launcher. The simplest design found:
- Start the backend only when the configured URL's host is loopback and
  nothing answers there, on that URL's own ports.
- Never take over a backend the app didn't start.
- Stop it on exit through a stdin-EOF flag (`--exit-with-parent`), since signals
  don't reach child processes on Windows.
- Move uploads (`settings.BASE_DIR / "uploads"`) to a configurable, writable
  folder first.
