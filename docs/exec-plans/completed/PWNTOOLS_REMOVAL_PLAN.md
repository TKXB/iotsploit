# Plan: Remove pwntools from All Components

## Status and Decision

**Direction: approved for implementation, with the corrections in this plan.**

The repository uses a small part of pwntools: an ADB wrapper, two SSH wrappers,
and terminal-mode workarounds. Replacing those uses with the `adb` executable
and Paramiko reduces dependency weight and removes the non-TTY failure mode.

This document authorizes the plan only. Implement the changes in a separate
step after review/approval of this revised plan.

## Verified Current Scope

Runtime imports and guards exist in:

- `iotsploit-django/src/iotsploit_django/tools/adb_mgr.py`
- `iotsploit-django/src/iotsploit_django/tools/ssh_mgr.py`
- `iotsploit-exploits/src/iotsploit_exploits/plugin_ssh.py`
- `iotsploit-cli/src/iotsploit_cli/console.py`
- `iotsploit-core/src/iotsploit_core/core/exploit_manager.py`
- `iotsploit-exploits/src/iotsploit_exploits/adb_check/adb_check.py`

Active dependency declarations exist in:

- root `pyproject.toml` and `poetry.lock`
- `iotsploit-django/pyproject.toml`
- `iotsploit-cli/pyproject.toml`
- `iotsploit-exploits/pyproject.toml`
- root `requirements.txt`, which declares both `pwntools` **and a separate
  `pwnlib` entry**

Historical packaging documents also mention pwntools. They are not runtime
dependencies, but should be corrected or explicitly marked historical so that
repository-wide searches are unambiguous:

- `docs/PLUGIN_PACKAGING_PLAN.md`
- `docs/PLUGIN_PACKAGING_TODO.md`

## Options Considered

| Criteria | A: Keep pwntools | B: Direct replacement (recommended) | C: New shared transport abstraction |
|---|---|---|---|
| Approach | Retain current APIs and terminal guards | Use argument-list `subprocess` for ADB and Paramiko for SSH | Introduce shared ADB/SSH ports and adapters first |
| Code impact | Low | Medium | High |
| Dependency reduction | None | High | High |
| Regression risk | Existing failures remain | Manageable with contract tests | Higher due to broad refactor |
| Maintenance | Heavy dependency for narrow use | Standard, familiar APIs | Cleaner eventually, but speculative now |
| Recommended when | Removal is no longer a goal | Current task | Multiple interchangeable transports are required |

**Recommended option: B.** It removes pwntools with focused changes. Do not add
a general transport abstraction in this work; the two SSH managers can use the
same behavioral contract without forcing a cross-package refactor.

## Compatibility Contracts

Preserve these public method signatures and return conventions unless a test
below explicitly documents a correction:

- `ADB_Mgr.list_devices()` returns objects with at least a `.serial` attribute.
  Raw strings are not compatible with current callers in `adb_mgr.py` and
  `adb_check.py`.
- `ADB_Mgr.connect_dev()` returns the resolved serial on success and `None` on
  connection/root transition failure.
- ADB file methods retain their existing success/failure values.
- `SSH_Mgr.open_ssh()` returns a context on success and `None` on failure.
- `SSH_Mgr.ssh_cmd()` accepts a command string and returns decoded output on
  success or `None` on connection/command failure.
- `SSH_Mgr.close_ssh()` remains safe for `None` and is idempotent in practice.

Do not preserve pwntools-specific context attributes such as `.host`, `.user`,
`.connected()`, `.system()`, or `.process()`; no downstream caller relies on
them. The Django SSH manager is already internally inconsistent because
`open_ssh()` returns a process tube while the other methods expect a pwntools
SSH object.

## Phase 1: Add Focused Contract Tests

Add tests before changing implementations. Existing ADB permission tests mock
`shell_cmd()` and do not cover the migration boundary.

### ADB tests

Mock `subprocess.run`; never require hardware or a running ADB server.

- parse representative `adb devices -l` output, ignoring the header, blank
  lines, daemon startup text, malformed rows, and non-`device` states such as
  `offline` and `unauthorized`
- verify returned items expose `.serial`
- verify every device-specific invocation uses `adb -s <serial>` as an
  argument list, with no `shell=True`
- cover `wait-for-device`, root/unroot, pull, push, install, uninstall, and
  simple shell commands
- cover timeout, missing `adb` executable, and non-zero exit behavior
- cover local and remote temporary-script cleanup when script execution fails
- cover serial/path/command values containing spaces or shell metacharacters
  to prove that host-shell injection is not introduced

### SSH tests

Mock `paramiko.SSHClient` and its streams/channels; never open a network
connection.

- verify connect arguments, timeout, authentication failure, and cleanup after
  a partial connection failure
- verify command execution reads stdout and stderr and waits for exit status
- define non-zero exit behavior consistently for both SSH managers: log the
  decoded stderr and return `None`
- verify UTF-8 decoding uses an explicit error policy
- verify `close_ssh(None)` and repeated close calls are harmless
- add a plugin test proving a non-zero remote command produces a failed
  `ExploitResult`

## Phase 2: Replace pwntools ADB

**File:** `iotsploit-django/src/iotsploit_django/tools/adb_mgr.py`

1. Remove the pwntools imports and `PWNLIB_NOTERM` setup. Add only required
   standard-library imports (`subprocess`, `tempfile`, and a small record type
   such as a frozen dataclass or `NamedTuple`).
2. Add one private runner with an optional serial, for example
   `_run_adb(args, *, serial=None, timeout=...)`. `list_devices()` cannot use a
   helper that always inserts `-s` because no device is selected yet.
3. Build commands exclusively as argument lists:
   `['adb', '-s', serial, ...]`. Use `capture_output=True`, `text=True`, a
   finite timeout, and explicit non-zero handling. Never interpolate untrusted
   values into a host shell command.
4. Parse `adb devices -l` into a local compatibility record containing at
   least `serial`, `state`, and parsed detail fields. Return only devices in
   state `device`, matching the meaning expected by current availability
   checks; log skipped states at debug/warning level.
5. Replace global `context.device` usage with explicit serial selection for
   every command.
6. Replace all pwntools calls:

| Current operation | Replacement |
|---|---|
| `adb.devices()` | `adb devices -l` plus compatibility-record parser |
| `adb.wait_for_device()` | `adb -s <serial> wait-for-device` |
| `adb.root()` / `adb.unroot()` | corresponding device-specific commands |
| pull/push/install/uninstall | direct device-specific ADB argument lists |
| `adb.process([...])` | `adb -s <serial> shell -- <argv...>` where the command is already tokenized |
| makedirs/write/script execution | remote `mkdir -p`, local named temp file, push, `sh <remote-script>` |

7. Migrate `install_apk()` too. Its current formatted command is a host-shell
   injection risk and should not remain as the only ADB path through
   `Bash_Script_Mgr`.
8. For arbitrary `shell_cmd()` strings, retain the script-file design so pipes,
   redirects, and compound Android-shell expressions preserve their current
   meaning. Create the local temp file securely, push it, execute it with
   `sh`, and remove both local and remote files in `finally` blocks. Use a
   per-call unique remote name to prevent concurrent calls from overwriting a
   shared script.
9. Replace the single global “last serial/root” assumption. The singleton lock
   currently protects construction only and does **not** make device state
   thread-safe. Track root state per serial and guard same-device root/unroot
   transitions and command startup with a lock. Explicit `-s` selection removes
   the more serious global-device race formerly caused by `context.device`.
10. Catch expected boundary exceptions (`FileNotFoundError`,
    `subprocess.TimeoutExpired`, and `subprocess.CalledProcessError`) before the
    existing broad safety net, preserving current public return values and
    producing actionable logs.

## Phase 3: Replace Both SSH Implementations with Paramiko

**Files:**

- `iotsploit-django/src/iotsploit_django/tools/ssh_mgr.py`
- `iotsploit-exploits/src/iotsploit_exploits/plugin_ssh.py`

For each manager:

1. Remove pwntools imports and terminal environment setup; import Paramiko.
2. Construct `paramiko.SSHClient`, set the host-key policy, and call
   `connect(ip, username=user, password=passwd, timeout=...,` plus explicit
   authentication/banner timeouts if supported by the chosen minimum version).
3. Use `exec_command(command, timeout=...)`. Read stdout and stderr, obtain
   `recv_exit_status()`, decode consistently, and return `None` on a non-zero
   exit or transport exception.
4. Close a newly created client if connection fails. Make normal close simple
   and safe. Remove the unused/broken `__ssh_dict` and pwntools-specific
   connectivity checks unless tests demonstrate a real caching requirement.
5. Annotate contexts as `paramiko.SSHClient`; retain `Any` only in tests or at
   unavoidable plugin boundaries.

`AutoAddPolicy` matches the old `StrictHostKeyChecking=no` behavior and is the
compatibility choice for this migration, but it does not authenticate the
server. Document this security trade-off in code. A known-hosts policy is a
separate behavior change and should be configurable in later work.

Avoid adding a shared SSH base class in this change. Duplication is small, the
implementations live in separately packaged components, and a new abstraction
would expand the migration without a demonstrated second backend.

## Phase 4: Remove Terminal Workarounds

- Remove `from pwnlib import term` and the `term.term_mode = False` block from
  `iotsploit-cli/src/iotsploit_cli/console.py`.
- Remove `PWNLIB_NOTERM` setup from:
  - `iotsploit-core/src/iotsploit_core/core/exploit_manager.py`
  - `iotsploit-exploits/src/iotsploit_exploits/adb_check/adb_check.py`
- Remove `os` imports only where `rg` confirms they are otherwise unused.

Do this after transport replacements so intermediate commits remain importable.

## Phase 5: Correct Dependency Ownership and Metadata

1. Replace pwntools with a consistent Paramiko constraint in the components
   that import it directly:
   - `iotsploit-django/pyproject.toml`
   - `iotsploit-exploits/pyproject.toml`
2. Remove pwntools from:
   - root `pyproject.toml`
   - `iotsploit-cli/pyproject.toml`
3. Remove **both** `pwntools==4.12.0` and `pwnlib==8.6.8.6` from
   `requirements.txt`; retain its Paramiko pin.
4. Regenerate the root `poetry.lock` with Poetry. Confirm pwntools and its
   now-orphaned transitive-only packages leave the lock. Do not hand-edit the
   lockfile.
5. The nested `iotsploit-core/poetry.lock` has no matching active declaration;
   leave it unchanged unless verification finds pwntools in it.
6. Update stale dependency examples/inventory in
   `docs/PLUGIN_PACKAGING_PLAN.md` and `docs/PLUGIN_PACKAGING_TODO.md`, or label
   them as historical snapshots if preserving old decisions is intentional.

Paramiko must be declared by every distributable package that imports it,
regardless of whether it happens to be installed transitively in the current
root environment.

## Phase 6: Verification

Run fast focused checks first, then the required repository gate:

```bash
poetry check --lock
poetry run pytest iotsploit-django/src/iotsploit_django/tests/test_adb_mgr.py
poetry run pytest <new-ssh-test-paths>
tools/testing/test-python-full.sh
```

Use `rg`, not `grep`, for the removal audit. Audit active code/config separately
from documentation so this plan's discussion of pwntools does not create a
false failure:

```bash
rg -n "from pwn|import pwn|pwnlib|PWNLIB_NOTERM|pwntools" \
  --glob "*.py" --glob "*.toml" --glob "*.txt" \
  --glob "!docs/**" .
rg -n "pwntools|pwnlib" poetry.lock iotsploit-core/poetry.lock
```

If dependency installation or lock regeneration changes the environment, also
run import smoke tests for the independently packaged Django, CLI, and exploits
components through Poetry.

## Acceptance Criteria

- No active Python source imports `pwn`, `pwnlib`, or pwntools.
- No active dependency manifest, requirements file, or lockfile contains
  pwntools or the standalone `pwnlib` requirement.
- `list_devices()` preserves the `.serial` caller contract and handles common
  ADB states deterministically.
- Every device-specific ADB command uses explicit `-s <serial>` selection and
  no host-shell interpolation.
- Arbitrary Android shell commands retain pipes/redirection behavior and clean
  up unique temporary scripts on success and failure.
- Both SSH managers close failed connections, report non-zero remote exit
  status as failure, and expose no pwntools-specific API assumptions.
- Mock-based ADB and SSH contract tests pass without hardware/network access.
- `poetry check --lock` and `tools/testing/test-python-full.sh` pass; report
  passed, failed, skipped, and warning counts per repository policy.

## Out of Scope

- Changing public ADB/SSH manager method signatures
- Replacing the `adb` system executable or adding an embedded ADB library
- Introducing a general transport/plugin abstraction
- Enforcing SSH known-host verification without a credential/configuration
  design
- Hardware validation in the deterministic test gate; record a separate manual
  rig smoke test for list/connect/root/shell/push/pull and SSH when hardware is
  available
