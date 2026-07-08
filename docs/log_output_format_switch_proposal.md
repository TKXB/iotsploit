# Log Output Format Switch Proposal

## Problem

The interactive `iotsploit` shell currently prints operational messages through
the same logger format used for service logs:

```text
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | Waiting for task to complete...
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | Async plugin execution completed
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | Plugin execution result:
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | status: success
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | message: WiFi backend not available. Ensure PluginContext was injected.
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | data: {}
```

This is useful for debugging and service logs, but too noisy for an interactive
CLI. The timestamp, log level, and full logger path make normal task output hard
to scan.

### Two logging systems, not one

The shell prints operational output through **two independent loggers**, and any
format switch must account for both or it will only clean up half the output:

- `IotsLogger` (`iotsploit_core.utils.iots_logger`, logger prefix `iots.`).
  All eight CLI command modules (`plugin_commands`, `device_commands`,
  `system_commands`, `target_commands`, `network_commands`, `linux_commands`,
  `firmware_commands`, `django_commands`) log through this. The noisy example
  above comes from here.
- `XLogger` (`iotsploit_django.tools.xlogger`, exported as `xlog`). The shell
  entrypoint `console.py` imports `from iotsploit_django.tools.xlogger import
  xlog as logger` and uses it for **all** startup, target/device-init, and
  device-lifecycle messages (e.g. "No targets found in database...",
  "Automatic device initialization started...", "Successfully connected ...").

If only `IotsLogger` is switched, plugin/command output goes clean while the
shell's own lifecycle chatter stays fully verbose — mixed output that misses the
goal. This proposal therefore switches **both** console loggers, while keeping
the WebSocket/Flutter console channel on `standard` (see below).

`XLogger` also attaches a `_ConsoleBufferWSHandler` that formats records with a
hardcoded string and pushes them to the Flutter UI over WebSocket. That handler
is the "service log" channel and must **not** follow the console format switch;
only the terminal `StreamHandler` formatters change.

## Goals

- Keep the current detailed format as the default for backward compatibility.
- Add an explicit user switch for cleaner shell output.
- Support both startup configuration and runtime changes inside the shell.
- Keep implementation centralized in logger setup instead of editing each
  command's output calls.
- Make the same concept available to MCP logging, but keep CLI and MCP
  configuration independent.
- Apply the switch to **both** console loggers (`IotsLogger` and `XLogger`) so
  the shell's own lifecycle output is cleaned up along with command output.
- Preserve color output in interactive terminals — the switch changes the format
  string, not whether colorlog is used.

## Non-Goals

- Do not remove structured service logs.
- Do not change Django's existing `LOGGING` dictionary in the first step.
- Do not rewrite command handlers to replace `logger.info(...)` with
  `poutput(...)`. (Note: because output rides on the logger, all formats emit to
  **stderr**, not stdout — fine for interactive use, but not pipe-friendly like
  `poutput`.)
- Do not hide warnings, errors, or tracebacks when debug logging is enabled.
- Do not change the WebSocket/Flutter console format (`_ConsoleBufferWSHandler`);
  it stays `standard` so the UI console keeps structured records.

## Proposed UX

### CLI Flags

Add log format flags to `iotsploit`:

```bash
iotsploit --log-format standard
iotsploit --log-format compact
iotsploit --log-format plain
iotsploit --plain-log
```

`--plain-log` is shorthand for `--log-format plain`.

### Environment Variable

Allow persistent configuration:

```bash
IOTSPLOIT_LOG_FORMAT=plain iotsploit
IOTSPLOIT_LOG_FORMAT=compact iotsploit
```

### Interactive Shell Command

Extend the existing shell logging command:

```text
set_log_format standard
set_log_format compact
set_log_format plain
```

Add a short alias:

```text
slf plain
```

Keep the existing level command unchanged:

```text
set_log_level DEBUG
sll DEBUG
```

## Formats

### `standard`

Current behavior. Best for debugging, CI logs, and service processes.

```text
2026-07-08 14:43:55 | INFO | iots.iotsploit_cli.commands.plugin_commands | Waiting for task to complete...
```

### `compact`

Keeps severity, removes timestamp and module path.

```text
INFO | Waiting for task to complete...
```

### `plain`

Message only. Best for normal interactive shell use.

```text
Waiting for task to complete...
```

Expected output for the example:

```text
Waiting for task to complete...
Async plugin execution completed
Plugin execution result:
status: success
message: WiFi backend not available. Ensure PluginContext was injected.
data: {}
```

## Implementation Plan

### 1. Core Logger (`IotsLogger`)

Update `iotsploit-core/src/iotsploit_core/utils/iots_logger.py`.

Add **two** parallel format tables — one plain, one color — because
`_create_console_handler` uses `colorlog.ColoredFormatter` (which needs a
`%(log_color)s` prefix) when `self._use_color` is true, and a plain
`logging.Formatter` otherwise:

```python
LOG_FORMATS = {
    "standard": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    "compact": "%(levelname)s | %(message)s",
    "plain": "%(message)s",
}
COLOR_LOG_FORMATS = {
    "standard": "%(log_color)s%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    "compact": "%(log_color)s%(levelname)s | %(message)s",
    "plain": "%(log_color)s%(message)s",
}
```

Read the default format name from `IOTSPLOIT_LOG_FORMAT` in `_init_once`
(mirroring the existing `_get_env_level`) and store it as `self._default_format`,
defaulting to `"standard"`. An unknown value falls back to `"standard"`
(see "Invalid formats" below).

`_create_console_handler` must **stop hardcoding** `self.LOG_FORMAT` /
`self.COLOR_FORMAT` and instead build its formatter from `self._default_format`,
selecting `COLOR_LOG_FORMATS` or `LOG_FORMATS` based on `self._use_color`. This
is required so that any logger created *after* a runtime switch (or lazily during
a session) picks up the current format instead of reverting to `standard`.

Add a method:

```python
def set_format(self, fmt: str) -> None:
    ...
```

It must:

1. Validate `fmt` against `LOG_FORMATS`; silently ignore invalid input, matching
   the existing `set_level` behavior.
2. Store `self._default_format = fmt` so future loggers use it.
3. Re-set the formatter on every existing console `StreamHandler` in
   `self._loggers` (choosing the color or plain table per handler / `_use_color`).
   Leave any extra handlers (`self._extra_handlers`, e.g. file handlers) untouched.

### 1b. Shell Entrypoint Logger (`XLogger`)

Update `iotsploit-django/src/iotsploit_django/tools/xlogger.py` so the shell's own
lifecycle output honors the same switch.

- Add a `COLOR_LOG_FORMATS`-style table and a `set_format(fmt)` method analogous
  to `IotsLogger.set_format`.
- `get_logger` currently hardcodes the colorlog format string; change it to build
  from the current format name so newly created loggers match.
- **Only** update the terminal `colorlog.StreamHandler` formatter. Do **not**
  touch `_ConsoleBufferWSHandler` — its hardcoded `timestamp | LEVEL | name | msg`
  format feeds the Flutter/WebSocket console and must stay `standard`.
- Read the same `IOTSPLOIT_LOG_FORMAT` env var so CLI startup respects it.

### 2. CLI Entrypoint

Update `iotsploit-cli/src/iotsploit_cli/console.py`. The current `main()` parser
only defines `--runserver`; add:

```python
parser.add_argument(
    "--log-format",
    choices=["standard", "compact", "plain"],
    default=None,
)
parser.add_argument(
    "--plain-log",
    action="store_true",
    help="Use message-only log output in the interactive shell",
)
```

**Precedence** (resolve in `main()`):

1. `--log-format X` (explicit flag) wins.
2. else `--plain-log` implies `plain`.
3. else `IOTSPLOIT_LOG_FORMAT` env var.
4. else `standard`.

If both `--plain-log` and `--log-format` are given, `--log-format` wins (the
explicit choice); this is worth a one-line note in the flag help.

**Import-time ordering caveat.** `console.py` runs `discover_command_modules()`
at *module import* (before `main()` runs), and each command module calls
`iots_logger.get_logger(__name__)` at import. So by the time argv is parsed, many
`IotsLogger` handlers already exist. The resolved format must therefore be applied
via `iots_logger.set_format(...)` **and** `xlog.set_format(...)` inside `main()`
so both the already-created and future handlers are updated. The env-var default
still covers loggers created during import (they read `self._default_format` set
in `_init_once`).

### 3. Interactive Command

Update `iotsploit-cli/src/iotsploit_cli/commands/system_commands.py`, following
the existing `do_set_log_level` pattern (validate, offer `Input_Mgr` choice when
no arg, echo confirmation/error).

Add:

```python
def do_set_log_format(self, arg):
    ...

do_slf = do_set_log_format
```

Valid values:

```text
standard, compact, plain
```

The command must apply the format to **both** console loggers so shell and
command output stay consistent:

```python
iots_logger.set_format(selected_format)
xlog.set_format(selected_format)
```

On an invalid value, echo a red error listing valid choices (as
`do_set_log_level` does) rather than silently ignoring — the underlying
`set_format` ignores it silently, but the interactive command should tell the
user.

**Also register the command in the help category map.** `console.py` manually
maps `set_log_level` under `Shell Commands` in `self._cmd_to_category`
(the dict around lines 203–234). Add `set_log_format` (and, if desired, `slf`)
there, or it will land in `Uncategorized`.

### 4. MCP Logger

Update `iotsploit-mcp/src/iotsploit_mcp/tools/xlogger_mcp.py`.

Add a parallel environment variable:

```text
IOTSPLOIT_MCP_LOG_FORMAT
```

Supported values should match core:

```text
standard, compact, plain
```

MCP should keep `standard` as default because it usually runs as a service.

**Implementation notes for `xlogger_mcp.py`:**

- `_MCPLogConfig` is a **frozen** dataclass. Read `IOTSPLOIT_MCP_LOG_FORMAT` in
  `XLoggerMCP.__init__` (same pattern already used by `_env_level`) and construct
  the config with the resolved `fmt`; do not mutate the frozen instance.
- `get_logger` currently builds a **single** `formatter` and applies it to both
  the stream handler and the file handler. To honor "file stays `standard`,
  console can be `plain`", build **two** formatters: the console/stream handler
  uses the selected format; the `FileHandler` keeps `standard`. This resolves the
  Compatibility note below at the code level.

## Compatibility

- Default remains `standard`, so existing logs do not change unless a user opts
  in.
- `IOTSPLOIT_LOG_LEVEL` and `set_log_level` continue to work as-is.
- `plain` format changes appearance only; it must not change log filtering,
  exception logging, or command behavior.
- File handlers keep `standard` even when the console is `plain`. For MCP this is
  enforced by using two formatters (see MCP notes); for `IotsLogger`/`XLogger`,
  `set_format` only touches terminal `StreamHandler`s and leaves extra handlers
  (file, WS buffer) alone.
- Interactive TTY color is preserved: the switch selects a `%(log_color)s…`
  variant when colorlog is active, so `plain` in a terminal is still colored,
  just without the timestamp/level/name prefix.

## Suggested Defaults

- `iotsploit`: keep `standard` for compatibility, but document `--plain-log` as
  the recommended interactive mode.
- `iotsploit --runserver`: keep `standard`, because this mode starts services.
- `iotsploit-mcp`: keep `standard`, because it is a server process.

## Tests

Add focused tests for `IotsLogger`:

- Default format is `standard`.
- `IOTSPLOIT_LOG_FORMAT=plain` creates message-only output.
- `set_format("compact")` updates **already-created** logger handlers.
- A logger created *after* `set_format("plain")` also emits message-only output
  (guards the `_create_console_handler` change).
- Invalid format is **silently ignored** and leaves the current format unchanged
  (matches `set_level`). Decided: ignore, do not raise; the interactive command
  is responsible for user-facing errors.
- Color path: when `_use_color` is true, the emitted record still carries the
  colorlog prefix for each format (no color loss).

Add equivalent tests for `XLogger.set_format`, including that
`_ConsoleBufferWSHandler` output remains `standard` regardless of the console
format.

Add CLI smoke checks:

```bash
poetry run iotsploit --plain-log --help
poetry run iotsploit --log-format compact --help
```

**Acceptance criterion (catches the two-logger gap).** In `plain` mode, no line
emitted during a full shell session — from startup through a plugin run — should
contain a ` | ` level/name prefix. Concretely: capture stderr of a scripted
session started with `--plain-log` and assert no line matches
`^\d{4}-\d\d-\d\d .* \| (INFO|WARNING|ERROR) \|`. This fails if `XLogger`
(the `console.py` startup/device messages) is left unswitched.

## Documentation

Update package docs with:

```bash
IOTSPLOIT_LOG_FORMAT=plain poetry run iotsploit
poetry run iotsploit --plain-log
poetry run iotsploit --log-format compact
```

Also document MCP equivalents:

```bash
IOTSPLOIT_MCP_LOG_LEVEL=DEBUG IOTSPLOIT_MCP_LOG_FORMAT=compact poetry run iotsploit-mcp http
```

## Open Questions

- Should `plain` hide `INFO |` only, or also hide `WARNING |` and `ERROR |`?
  This proposal hides all prefixes for consistency, but `compact` remains
  available when severity should stay visible.
- Should Django HTTP logs respect `IOTSPLOIT_LOG_FORMAT`? That can be added in a
  later step by wiring the same format names into the Django `LOGGING`
  formatter.
- Should file logs always force `standard` even when console logs are `plain`?
  **Decided: yes** (see Compatibility).
- Invalid format at the API level: **decided** — `set_format` silently ignores
  it (consistent with `set_level`); interactive `do_set_log_format` surfaces the
  error to the user.
- `XLogger` scope: **decided** — the switch also applies to `XLogger` so the
  shell's own startup/device output is cleaned up; the WebSocket console handler
  stays `standard`.
