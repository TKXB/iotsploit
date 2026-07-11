# Testing Policy

## Commit-Time Gate

Before executing `git commit` for Python code, run:

```bash
tools/testing/test-python-full.sh
```

The script runs Ruff and then pytest, stopping on the first failure. All
test paths, import mode, markers, and exclusions are configured in root
`pyproject.toml` under `[tool.pytest.ini_options]`.

## Agent Responsibilities

1. **Stop and do not commit** when the runner exits non-zero.
2. **Fix failures caused by your changes** and rerun the complete gate.
3. **Report counts**: passed, failed, skipped, and warnings.
4. **Report environmental blockers** (missing services, missing hardware)
   rather than silently skipping required tests.
5. **Never delete, weaken, or skip an unrelated test** only to make the
   gate pass.
6. **Never use `git commit --no-verify`** without explicit user
   authorization.

## What The Gate Includes

- Ruff lint checks for tracked Python source and tests.
- All deterministic package unit tests.
- Root cross-package integration tests that require no external service.
- Root contract tests that require no physical hardware or running server.
- A non-zero exit status when any required check fails.

## What The Gate Excludes

- Physical hardware tests.
- Interactive diagnostics and prompts.
- Tests that modify real network or device state.
- Tests requiring manually started Redis, Django, or other services until
  those dependencies are made hermetic or explicitly provisioned by the
  runner.

## Test Markers

Registered in `pyproject.toml`. Unknown markers produce an error
(`--strict-markers`).

| Marker         | Description                                              |
| -------------- | -------------------------------------------------------- |
| `unit`         | Isolated, deterministic behavior.                        |
| `integration`  | Behavior involving multiple software components.          |
| `contract`     | HTTP, WebSocket, MCP, entry-point, or plugin compatibility. |
| `django`       | Behavior requiring Django initialization or its test database. |
| `service`      | Behavior requiring Redis or another external service.    |
| `hardware`     | Behavior requiring a physical device.                    |
| `interactive`  | Behavior requiring human input.                           |

Run a marked group directly: `poetry run pytest -m <marker>`.

## Git Enforcement

A tracked `tools/git-hooks/pre-commit` hook invokes the full runner. Enable
it in each working copy:

```bash
git config core.hooksPath tools/git-hooks
```

The hook provides local enforcement; this policy explains the required
behavior. A future CI workflow should invoke the same runner.

## Hardware Diagnostics

The interactive WiFi backend diagnostic lives at
`tools/hardware/manual_wifi_backend_check.py`. It is not collected by
pytest and must be invoked manually:

```bash
poetry run python tools/hardware/manual_wifi_backend_check.py --interface wlan0
# read-only mode:
poetry run python tools/hardware/manual_wifi_backend_check.py --interface wlan0 --safe-only
```

Never add hardware diagnostics back into a `tests/` directory.
