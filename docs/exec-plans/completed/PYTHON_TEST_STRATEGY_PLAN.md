# Python Test Strategy Plan

## Status

Implemented. Phases 1 and 2 are complete.

## Objective

Create one reliable Python test gate that every AI agent runs before committing
new Python code. The gate must execute all deterministic tests, block commits on
failure, and never trigger interactive or hardware-mutating operations.

## Current Baseline

The repository is a Poetry-based Python monorepo containing `iotsploit-core`,
`iotsploit-cli`, `iotsploit-django`, `iotsploit-mcp`, `iotsploit-platforms`,
`iotsploit-fuzzer`, `iotsploit-drivers`, and `iotsploit-exploits`.

The current deterministic suite contains 14 tests. It passes in approximately
one second with this collection mode:

```bash
poetry run pytest --import-mode=importlib -q \
  iotsploit-core/tests \
  iotsploit-django/tests \
  iotsploit-django/src/iotsploit_django/tests \
  iotsploit-fuzzer/tests \
  iotsploit-mcp/tests
```

The default combined collection currently fails because Django and fuzzer both
contain an un-packaged `tests/test_imports.py`. Root pytest configuration must
use `--import-mode=importlib` or those modules must be packaged or renamed.

`iotsploit-platforms/tests/test_wifi_backend_safe.py` is an interactive hardware
diagnostic rather than a pytest test suite. It can alter Wi-Fi connectivity and
must not be part of an automatic commit gate.

## Definition Of Full Test

The commit-time full test includes:

- Ruff checks for tracked Python source and tests.
- All deterministic package unit tests.
- Root cross-package integration tests that require no external service.
- Root contract tests that require no physical hardware or running server.
- A nonzero exit status when any required check fails.

The commit-time full test excludes:

- Physical hardware tests.
- Interactive diagnostics and prompts.
- Tests that modify real network or device state.
- Tests requiring manually started Redis, Django, or other services until those
  dependencies are made hermetic or explicitly provisioned by the runner.

## Target Structure

```text
tools/
├── testing/test-python-full.sh
├── hardware/manual_wifi_backend_check.py
└── git-hooks/
    └── pre-commit
```

Package-specific tests remain in each package's existing `tests/` directory.
Create a root `tests/` subdirectory only when the first real cross-package test
needs it. Do not create empty integration, contract, service, or hardware test
directories in advance.

`tools/testing/test-python-full.sh` is the only initial orchestration script. It
runs the required checks in order, stops on failure, and returns a combined
result. The interactive Wi-Fi diagnostic belongs under `tools/hardware/`
because it is a manual utility, not a pytest test.

## Test Categories

Register markers only when a real test first requires them. Expected categories
are:

- `unit`: isolated, deterministic behavior.
- `integration`: behavior involving multiple software components.
- `contract`: HTTP, WebSocket, MCP, entry-point, or plugin compatibility.
- `django`: behavior requiring Django initialization or its test database.
- `service`: behavior requiring Redis or another external service.
- `hardware`: behavior requiring a physical device.
- `interactive`: behavior requiring human input.

Unknown markers should produce an error. A marked group can be run directly
with `poetry run pytest -m <marker>`; it does not need a wrapper script. Add a
dedicated service or hardware runner only when it performs meaningful setup,
such as provisioning Redis or validating an attached device.

## Canonical Runners

`tools/testing/test-python-full.sh` will be the mandatory commit-time command.
Apart from normal shell safety setup, its work is intentionally limited to:

```bash
poetry run ruff check .
poetry run pytest
```

The exact test paths, import mode, markers, and exclusions belong in root pytest
configuration rather than being duplicated in the shell script.

## Commit Policy For AI Agents

Before executing `git commit` for Python code, Codex, Claude Code, and Cursor
must run:

```bash
tools/testing/test-python-full.sh
```

The agent must:

1. Stop and not commit when the runner fails.
2. Fix failures caused by its changes and rerun the complete gate.
3. Report passed, failed, skipped, and warning counts.
4. Report environmental blockers rather than silently skipping required tests.
5. Never delete, weaken, or skip an unrelated test only to make the gate pass.
6. Never use `git commit --no-verify` without explicit user authorization.

The canonical policy will live in `.agents/standards/testing.md`. `AGENTS.md`,
`CLAUDE.md`, and `.cursor/rules/00-workspace.mdc` will direct their respective
agents to that policy. `.agents/local.md` will record the local Poetry command
and any machine-specific, non-secret test prerequisites.

## Git Enforcement

A tracked `tools/git-hooks/pre-commit` hook will invoke the full runner. Each
working copy enables the hook with:

```bash
git config core.hooksPath tools/git-hooks
```

The hook provides local enforcement, while the agent instructions explain the
required behavior and failure handling. A later CI workflow should invoke the
same runner to verify a clean environment.

## Implementation Phases

### Phase 1: Normalize Collection

1. Add pytest explicitly to the root Poetry development dependencies.
2. Add root pytest configuration with `--import-mode=importlib`.
3. Include every deterministic package and nested Django test location.
4. Confirm the existing 14-test baseline passes from the repository root.

### Phase 2: Add The Commit Gate

1. Move the interactive Wi-Fi diagnostic outside pytest discovery, for example
   to `tools/hardware/manual_wifi_backend_check.py`.
2. Add clear manual invocation and safety requirements.
3. Create the single `tools/testing/test-python-full.sh` runner.
4. Create the tracked pre-commit hook and enable `core.hooksPath` locally.
5. Add the test policy to all three AI entry points.
6. Verify default collection performs no hardware initialization or prompts.
7. Test both a passing gate and a deliberately failing gate.

### Phase 3: Grow Only When Needed

1. Add tests for CLI, drivers, exploits, or cross-package behavior as code is
   changed or defects are found.
2. Create root test directories only alongside the first test placed in them.
3. Register a pytest marker only alongside tests that use it.
4. Add a specialized runner only when it must provision or validate an external
   dependency that a direct `pytest -m` command cannot handle.
5. Add CI using the same full runner after the local gate is stable.
6. Establish a coverage baseline before introducing any threshold.

## Acceptance Criteria

- `poetry run pytest` works from the root without manually listing packages.
- All existing deterministic tests pass and nested Django tests are included.
- Interactive Wi-Fi diagnostics are not collected by default.
- The full runner performs no hardware or real-network mutations.
- All three AI tools use the same pre-commit test command and policy.
- A failed full test blocks a normal commit.
- Hardware diagnostics require explicit manual invocation.
- The system Python and system `pip` are not used.
- The runner is reusable unchanged by a future CI workflow.

## Recommended Decision

Implement the canonical runner, shared AI policy, and local pre-commit hook
first. Add CI after the local gate and test classification are stable.
