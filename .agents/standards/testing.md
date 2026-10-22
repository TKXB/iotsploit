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

## Writing Tests

How to write a test, as opposed to how to run one. Read this before adding or
changing a test.

### Coverage

For the function or method under test, cover:

1. **Core behavior** — the main purpose, with realistic inputs and asserted
   return values. Use data shaped like real device, plugin, or target data.
2. **Input validation** — wrong types, `None`, empty `str`/`list`/`dict`, and
   boundary values (zero, negative, off-by-one at a documented limit).
3. **Error handling** — `pytest.raises` for the exceptions the contract
   promises, asserting on the message when the message is part of that
   contract.
4. **Side effects** — external calls made with the right arguments, state
   changes, and interaction with injected dependencies.

Five to eight focused cases is the target. Prefer more assertions on fewer
scenarios over near-duplicate tests, and use `@pytest.mark.parametrize` when
scenarios differ only in their data.

### Structure

- Arrange, Act, Assert, in that order, separated by blank lines.
- One behavior per test. A name that needs "and" is two tests.
- Name the scenario and the expectation:
  `test_facet_key_survives_uninstalled_plugin`, not `test_facet_2`.
- Group with a module or a class. pytest has no `describe`/`context` block.
- Tests must pass in any order. A fixture that mutates process-global state
  restores what was there rather than deleting what it added — see the `doip`
  fixture in `iotsploit-core/tests/test_facets.py`.

### Marking

Every test file declares its tier at module level, using the markers in the
table above:

```python
pytestmark = pytest.mark.unit
```

Multiple tiers take a list: `[pytest.mark.django, pytest.mark.integration]`.
`--strict-markers` makes an unregistered marker an error, but nothing catches
a *missing* one — an unmarked test silently escapes every `-m` selection, so
treat an absent `pytestmark` as a defect.

New test files belong under an existing `testpaths` entry in root
`pyproject.toml`. A file outside those paths is never collected.

### Mocking

- Inject the dependency when the code under test allows it. A fake object or a
  stub callable beats `unittest.mock.patch`.
- Use `monkeypatch` for environment variables and module attributes; it undoes
  itself.
- Patch at the point of use, not the point of definition.
- Never touch a real network, a real device, or a path outside `tmp_path`. A
  test that needs one belongs behind `service`, `hardware`, or `interactive`,
  and is then outside the gate.

### Documenting

State the rule a test protects in the module docstring whenever that rule is
not obvious from the assertions. `iotsploit-core/tests/test_facets.py` is the
model: it names the invariant and the consequence of breaking it, which is
what makes a failure diagnosable a year later.

Comment complex setup. Do not comment an obvious assertion.

Test behavior, not implementation. A test that breaks on a rename but not on
a behavior change is a liability.

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
