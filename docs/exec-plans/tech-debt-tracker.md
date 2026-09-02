# Tech Debt Tracker

Shortcuts and deferred work that no single plan owns. One entry per item: what
it is, what it costs while it stands, why it was left, and what closing it
takes. Move an entry to `## Closed` with the commit that closed it rather than
deleting it, so the reason a thing was tolerated stays readable.

UI-side debt lives in the `ui/` repository's own tracker.

## Open

### The Python backend is not installable as a complete native Windows application

**Found** 2026-08-30, during a repository-wide Windows compatibility audit.

**Where** The package boundaries disagree about Windows support:

- `iotsploit-core/pyproject.toml` has only portable direct dependencies
  (`pluggy` and `dataclasses-json`), and `iotsploit-core` has no unconditional
  Unix-only imports. The core package should install and run on Windows, though
  individual services still depend on the external tool or hardware backend
  they invoke.
- `iotsploit-django/pyproject.toml` unconditionally installs `bluepy` and
  `smbus2`. `bluepy` supports Linux only; `smbus2` imports Unix `fcntl` and
  operates through Linux I2C/SMBus interfaces. The optional
  `iotsploit-platforms` extra is not needed to encounter these blockers.
- The workspace `pyproject.toml` additionally installs `iotsploit-platforms`
  and `pyudev` without platform markers. `iotsploit-platforms` unconditionally
  installs the Linux NetworkManager dependencies `PyGObject` and
  `dbus-python`, while `pyudev` binds Linux `libudev`.
- The full Django application depends on Celery workers for queued,
  interactive, and streaming plugin execution. Celery has not supported
  Windows since 4.x. Django-owned feature paths also invoke `sudo`, Bash,
  `os.geteuid()`, Linux networking utilities, SocketCAN, BlueZ utilities, and
  Linux device interfaces.
- The CLI registers Unix-only `signal.SIGHUP` unconditionally, so even an
  environment assembled by manually omitting incompatible dependencies cannot
  start through the normal `iotsploit` entry point on Windows.

The practical boundary is therefore narrower than the product's Windows UI
support suggests: `iotsploit-core` is portable, and a reduced Django HTTP/ASGI
subset is likely portable after dependency separation, but the declared Django
package and complete root application are not. No Windows CI job currently
tests even that reduced subset.

**Why it stands** The deployed Python backend runs on the Linux hardware rig,
while Windows support has applied to the desktop UI. The package metadata and
CI do not encode that split, so installing the root project implies a native
Windows backend capability that the runtime does not provide.

**Closing it** First decide and document one support contract: either keep the
Python backend Linux-only and make Windows a remote UI/client, or support a
native Windows web-only backend. For the web-only contract, add platform
markers or hardware extras for `bluepy`, `smbus2`, `pyudev`, PyGObject, and
`dbus-python`; guard the CLI's signal and process-group handling; and add a
Windows CI job covering installation, import, Django checks, and ASGI startup.
Full native feature parity is a separate, substantially larger project: it
requires a supported Windows task-execution owner in place of Celery plus
Windows backends for privilege management, Wi-Fi, CAN, Bluetooth, SPI/I2C, and
the Bash/Linux-command features.

### An interactive execution can be queued behind one nobody can answer

**Found** 2026-08-20, while fixing the Plugins page (`iotsploit-ui@f218756`).

**Where** `iotsploit-django/src/iotsploit_django/view_handlers/plugin_views.py`
(`execute_plugin`), against the `interactive` queue served at `-c 1`.

`execute_plugin` creates a `PluginExecution` and enqueues it unconditionally,
including while another run is already `waiting_input`. The queue serves one run
at a time -- deliberately, so the Control Panel can show a single unambiguous
question -- so a second launch is accepted, queued, and then invisible: the
client shows "running" with no prompt and no timeout until the first run's
prompt expires (300s by default). Every report of this so far has been read as
"the Control Panel is broken".

**Why it stands** The client that could create an orphan has been fixed, so the
common path no longer produces one. This is the backstop for the paths that
remain (a reload, a second operator, a direct API caller).

**Closing it** Refuse the launch with 409 when an interactive execution is
already `running` or `waiting_input`, returning that `execution_id` so the
caller can attach to the open prompt instead of starting a rival run. The
invariant is currently emergent from the worker's concurrency; this makes it
explicit at the boundary that can enforce it.

### `sweep_stranded_executions` is written but never runs

**Found** 2026-08-20.

**Where** `iotsploit-django/src/iotsploit_django/tasks/interaction_tasks.py`,
`.../adapters/django/interaction/service.py` (`sweep_stranded`, `SWEEP_GRACE`).

There is no beat process and no `CELERY_BEAT_SCHEDULE`; `runserver` starts two
workers and nothing else (`iotsploit-cli/.../django_commands.py`). So a run
whose worker died with a prompt open stays `waiting_input` forever with its
`InputRequest` still `PENDING`. `SWEEP_GRACE`, the `worker_lost` reason, and the
`expired` event are all unreachable today, and `/api/plugin-executions/pending/`
will hand ghosts to the first client that consumes it.

**Why it stands** Nothing consumes the pending endpoint yet, so the ghosts are
not visible in the product.

**Closing it** Schedule the task (beat alongside the two workers, or an
equivalent periodic trigger) at roughly the sweep grace. Related: the task runs
with `acks_late` unset, so a restart silently discards a reserved-but-unstarted
run; turning it on with `reject_on_worker_lost` needs the sweep in place first
to retire the duplicate that redelivery creates.

## Closed

_None yet._
