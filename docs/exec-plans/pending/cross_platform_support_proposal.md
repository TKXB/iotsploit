# Cross-Platform Support Proposal (Windows and macOS)

## Status

- **State:** Phases 0–4 implemented in the working tree; **not yet validated on
  Windows or macOS** — see section 10
- **Draft date:** 2026-09-03
- **Revised:** 2026-09-03 after review — see section 9 for what changed and why
- **Implemented:** 2026-09-03, uncommitted on branch `dev`
- **Basis:** Static read of the tree at commit `3f207b8`; the code now differs
- **Estimated effort:** ~18 engineering days across 5 phases
- **Decision owner:** User
- **Remaining:** the six-step acceptance run in section 5.1, on the Windows 11
  guest. Everything before it is done and both gates are green on Linux.

**Goal.** Every package installs and imports on Linux, macOS and Windows.
Features that need Linux hardware, the privileged helper, or a POSIX process
model report themselves as unavailable — with a reason — instead of vanishing
from the plugin list or raising a traceback.

## Governing Standards

- `AGENTS.md` — **Delete > Replace > Add.** This proposal deletes two
  dependencies (`netifaces`, `smbus2`), a dead vendored module (`INA219.py`),
  and a duplicate binary resolver. Net line count is negative outside the one
  new module.
- `AGENTS.md` — **Solve at the owner.** Portability is decided in the adapter
  row and in the two managers that already own entry-point loading. No
  `if WINDOWS:` branches are added to plugins or to core services.
- `AGENTS.md` — **Search and reuse first.** Four pieces of the mechanism already
  exist in the tree; this proposal wires them up rather than adding a parallel
  abstraction.
- `docs/architecture.md:20-22` — **Core never picks its own adapter.** Core
  defines the availability value type and a resolver *port*; the concrete
  probing adapter is injected at the two existing composition roots.

## 1. Why this is cheap

This is not a port. The hard architectural work is done: `docs/architecture.md`
already forbids core from importing OS-specific libraries, and the codebase
mostly honours it. Four pieces of the mechanism exist today.

- `iotsploit-core/src/iotsploit_core/platforms/consts.py` already exports
  `LINUX / DARWIN / WINDOWS / BSD`. It currently has **zero call sites** outside
  its own package — an unused seam waiting to be used.
- `iotsploit-platforms/src/iotsploit_platforms/adapters/platforms/` already has
  `linux/`, `darwin/` and `windows/` WiFi backends, dispatched at import by
  those constants. The non-Linux ones are 93-line stubs raising
  `NotSupportedError` per method — exactly the right shape.
- `iotsploit-platforms/src/iotsploit_platforms/selector.py::build_context()`
  already degrades a backend that will not load to `wifi=None` with a warning
  rather than failing the whole context. `core_container._context_factory`
  degrades further to a bare `PluginContext`.
- `iotsploit-core/src/iotsploit_core/core/tool_manager.py` already resolves
  external binaries cross-platform, with a per-tool `platforms` list, Windows
  `.exe` handling, and a `ToolStatus` enum including `MISSING` and `INVALID`.
  It is wrapped by `core/tool_service.py`, which `nmap_scan` and
  `hydra_ssh_attack` already go through.

## 2. What actually breaks today

Four failure classes, in the order a user hits them.

### 2.1 Class A — install fails before any code runs

| Item | Detail |
|------|--------|
| `iotsploit-platforms` | Declared a **mandatory** path dependency in the root `pyproject.toml`, and hard-requires `PyGObject<3.51` + `dbus-python`. Both need GLib/girepository and libdbus headers. `poetry install` stops here on Windows and macOS. |
| `netifaces = 0.11.0` | Unmaintained C extension, no wheels for current CPython on Windows. Three call sites: `monitor_mgr.py:57-59`, `vehicle_utils.py:158`, and a lazy import in `someip/sd.py:335-357` that already catches `ImportError`. `psutil` is already a direct dependency of `iotsploit-django` and covers all three. |
| `smbus2 >= 0.4` | Declared in `iotsploit-django/pyproject.toml:52` with **zero call sites**. The only i2c code is `tools/third_party/INA219.py`, which imports the *different, undeclared* `smbus` package and is itself referenced by nothing. Both are deletions, not markers. |
| `pyudev` | Linux-only (libudev) but declared unconditionally. `spidev` is already correctly behind an extra. |

### 2.2 Class B — import-time crashes

| Location | Problem |
|----------|---------|
| `iotsploit-priv/src/iotsploit_priv/native.py:4,8` | `import grp` / `import pwd` at module top. `iotsploit-cli/.../priv_commands.py:9` imports it at module top, so the **entire CLI command set** fails to register. |
| `iotsploit-drivers/.../ft2232/drv_ft2232.py:9` | `import pyudev` at module top, in a driver whose USB half works fine elsewhere. |
| `iotsploit-cli/.../console.py:586` | `signal.signal(signal.SIGHUP, …)`. `SIGHUP` does not exist on Windows; the CLI entrypoint raises `AttributeError` on startup. |
| `iotsploit_platforms/platforms/__init__.py` | Raises `NotSupportedError` at import time for any platform outside the big three. |
| `iotsploit-priv/tests/test_native.py:5` | Imports `iotsploit_priv.native` at module top, so **pytest collection itself** fails on Windows. Marker filtering does not help: pytest imports a test module before it can deselect by marker. |

### 2.3 Class C — runtime crashes that bypass the designed error path

- **`iotsploit-priv/client.py:108`** constructs `socket.socket(socket.AF_UNIX, …)`.
  CPython does not expose `AF_UNIX` on Windows, so this raises `AttributeError` —
  which the `except (OSError, TimeoutError)` below it does not catch. Every
  privileged path (`drv_socketcan`, `doip_mgr`, `ip_scan`, `priv_check`) shows a
  traceback instead of the carefully written `PrivilegedHelperUnavailable`
  message.
- **Hardcoded POSIX paths:** `/tmp/sat_logs` (`django_commands.py:33`,
  `picocom_serial_reader.py:27`, `xlogger_mcp.py:23`), `/tmp/fuzzer_results`
  (`iot_fuzzer_service.py:854`), `/tmp/fuzzer_output`, `/sys/class/net`
  (`protocols/canbus/socketcan.py:349`, `demo/priv_check.py:98`),
  `/sys/class/thermal/thermal_zone0/temp` (`monitor_mgr.py:104`).
- **`os.killpg(os.getpgid(...))`** and `start_new_session=True` in
  `django_commands.py:223,323` and `net_audit_mgr.py:145` — absent or a no-op on
  Windows, so service shutdown leaks processes.
- **`select.select([proc.stdout], …)`** in `drv_ubertooth.py:138` — on Windows
  `select` accepts sockets only.
- **23 literal** `/dev/ttyUSB0` / `/dev/ttyACM2` defaults across drivers,
  exploits, fuzzer and Django views. The Windows equivalent is `COM3`.
- **External binaries bypassing ToolManager:** `["ip", …]` in `can_link.py:135`,
  `["adb"]` in `adb_mgr.py:103`, `"bash"` inserted at argv[0] in
  `bash_script_engine.py` (two sites), `sudo` in `priv_commands.py:60`.
  Separately, `net_audit_mgr._binary()` is a second, parallel `shutil.which`
  resolver duplicating ToolManager's `PathResolver`.
- **`LinuxCommands`** (`do_ls`, `do_lsusb`) is registered unconditionally on
  every platform.

### 2.4 Class D — the silent one

Both `exploit_manager._discover_entry_point_plugins` and its device-driver twin
already wrap each `entry_point.load()` in `try/except Exception`. On a non-Linux
host that is not resilience, it is **data loss**: the plugin is logged at error
level and then dropped, `disable_missing()` marks it gone, and the operator sees
a shorter list with no explanation.

This is the behaviour the proposal changes.

## 3. Proposed mechanism

### 3.1 Three tiers, because they have different lifetimes and different costs

A single `probe(name)` cached for the process lifetime is wrong: the same call
would have to answer "is this OS supported" (never changes) and "is the device
plugged in" (changes constantly, and answering it may claim exclusive hardware
or trigger a permission prompt). Split by lifetime:

| Tier | Question | Cost | Cached | Evaluated at |
|------|----------|------|--------|--------------|
| **1 — compatibility** | Is this OS supported? Is the Python module importable? | Free | Process lifetime | Discovery |
| **2 — prerequisites** | Is the binary on PATH? Is the privileged helper reachable? Does the CAN interface exist? | Cheap, no side effects | Short TTL, invalidated on demand | Listing |
| **3 — readiness** | Is the device connected and openable? | Expensive, **has side effects** | Never | `scan()` / `execute()` only |

**Tier 3 is not part of listing.** The existing driver `scan()` already owns
device enumeration via `conf/usb_devices.json` VID/PID matching; that stays the
owner. Nothing in this proposal opens a device to render a list.

This also corrects a mitigation in the first draft that said probes should "open
the device". They must not. Tier 1 and 2 are what CI can keep honest; tier 3 is
what a hardware rig keeps honest.

### 3.2 Core owns the value type and the port, not the probing

`docs/architecture.md:22` — core never picks its own adapter. So:

```python
# iotsploit-core/src/iotsploit_core/platforms/capability.py  (stdlib only)

@dataclass(frozen=True)
class Availability:
    available: bool
    reason: str      # "" when available, else why — in the operator's words
    hint: str        # what to do about it, or "" when nothing can be done

class CapabilityResolver(Protocol):          # the port
    def resolve(self, requirements: Sequence[str]) -> Availability: ...

def static_compatibility(requirements) -> Availability | None:
    """Tier 1 only: sys.platform + importlib.util.find_spec. Stdlib, no
    adapter selection. Returns None when tier 1 cannot decide."""
```

Tier 1 needs only `sys.platform` and `importlib.util.find_spec`, so it is
stdlib and stays in core. **Tiers 2 and 3 move out**: the concrete resolver
lives in `iotsploit-platforms` (which may import pyserial, python-can, pyudev
and `iotsploit_priv`) and is injected at the two composition roots that already
exist — `iotsploit_django/composition_root/core_container.py` and
`iotsploit_mcp/composition_root.py`.

The first draft also put `default_serial_port()` in core calling
`pyserial.tools.list_ports`. Core does not depend on pyserial
(`iotsploit-core/pyproject.toml:26-28`), and a generic "first serial port, else
`COM3`" default is dangerous anyway — it can select unrelated hardware. **That
helper is dropped.** The literal `/dev/ttyUSB0` defaults instead resolve through
the existing VID/PID driver discovery, which already knows which port belongs to
which device.

### 3.3 Requirements are static and persisted; availability is neither

This is the correction that matters most for a distributed deployment.
`iotsploit-mcp` reads plugin metadata from Django over HTTP and then executes
**locally**, and its repository already refuses to write back:
`HttpPluginMetaRepository.upsert()` is a deliberate no-op
(`http_plugin_meta_repo.py:49-52`) so that one node cannot overwrite global
state. Under `IOTSPLOIT_RUNTIME == "distributed"` the Celery worker is a third
host again.

So availability is **execution-node-specific and must never be persisted**:

- `PluginMeta` gains `requirements: tuple[str, ...]` — static, host-independent,
  safe in the database.
- `Availability` is **computed by the process serving the request**, attached to
  the REST response, and thrown away. Nothing writes it.
- The **final gate is in the executor**, not the dispatcher: `execute()`
  re-resolves requirements in the worker process immediately before running and
  returns a structured error if they are unmet. A Django dispatcher on Linux
  must not authorise a run on a Windows worker on the strength of its own probe.
- MCP computes availability locally over the metadata it fetched. Its `upsert()`
  stays a no-op.

### 3.4 Two discovery paths, because a failed import has no class to read

Both managers call `entry_point.load()` *before* they can inspect the class
(`exploit_manager.py:272`, `device_manager.py:192`). A class attribute is
therefore unreachable in exactly the case that motivates this work. The answer
is that the two cases need different sources, and the failing case needs no
declaration at all:

- **Import succeeded** → read `REQUIRES` off the class. This covers the common
  case: the plugin imports fine but needs `nmap`, the privileged helper, or a
  CAN interface at run time.
- **Import failed** → record the entry from `EntryPoint.name` and
  `EntryPoint.value`, both available without loading, and use the exception as
  the reason. `ModuleNotFoundError: No module named 'pyudev'` *is* the
  explanation; no `REQUIRES` is needed to produce it. A small module→hint table
  ("pyudev is Linux-only") upgrades the message where we know better.

No new metadata channel, no second entry-point group.

### 3.5 Drivers need their own model — they are not PluginMeta

The first draft's "all 30 entries" quietly conflated two different systems.
Exploit plugins have `PluginMeta` and a repository. Device drivers do not:
`device_manager.py:206` stores **instances** in a plain dict
(`self.drivers[name] = driver_class()`), and `DriverStateRepository` persists
only enabled/disabled. Instantiation at discovery time is itself a third failure
point.

So the driver side needs its own small availability record and its own API path,
parallel to the exploit one but not shared with it. That is real additional work
and is why Phase 2 grew from 4 days to 7. The honest headline is **22 exploit
plugins and 8 drivers**, tracked separately — not "30 of 30".

### 3.6 The behavioural change, drawn

```
TODAY - the plugin is dropped silently

  entry point          plugin manager           except Exception
  drv_socketcan  --->  entry_point.load() --->  logger.error(...)
                          ImportError                  |
                                                    dropped
                                                       v
                                            +------------------------+
                                            |  plugin list: 24 / 30  |
                                            |  no reason given       |
                                            +------------------------+


PROPOSED - the plugin is registered, blocked, and explained

  entry point  ---> entry_point.load()
                          |
        import failed <---+---> import ok
              |                     |
        name + value          read REQUIRES
        + exception                 |
              |               tier 1 + tier 2 resolve
              |                     |            (on THIS node)
              +---------> Availability <---------+
                                |
                                v
                    +--------------------------+
                    |  listing: 22 exploits    |
                    |  + 8 drivers, each with  |
                    |  a reason when blocked   |
                    +--------------------------+
                                |
                        execute() re-resolves
                        in the worker process
```

The plugin never disappears — only its run button does, and the run button is
decided by the machine that would actually run it.

### 3.7 Where portability is decided

Because dependencies already point inward, no application or core module needs
to know what OS it is on. The entire operating-system surface is the adapter
row.

```
        iotsploit-cli       iotsploit-django        iotsploit-mcp
              |                     |                     |
              +---------------------+---------------------+
                                    |  depends on
                                    v
  +--------------------------------------------------------------+
  |  iotsploit-core - domain / ports / services                  |
  |  no OS imports, no Django, no hardware                       |
  |  platforms/consts.py                                         |
  |  platforms/capability.py  (new: value type + port + tier 1)  |
  +--------------------------------------------------------------+
                                    ^
                                    |  implements ports
          +-------------------------+-------------------------+
          |            |            |            |            |
      platforms     drivers     protocols    exploits       priv
      WiFi via        USB        SOME/IP       nmap        systemd
      Network-      serial        DoIP          adb        AF_UNIX
       Manager       udev          CAN          ip         socket
      + tier 2/3
        resolver
```

That bottom row is the whole surface area of the port. Per-OS availability for
each of those adapters is in the table in section 4.

### 3.8 One supporting helper

`runtime_dir()` / `log_dir()` in `iotsploit_core/utils/helpers.py`, built on
`tempfile.gettempdir()` and keeping today's env overrides, replacing the `/tmp`
literals. (The serial-port helper from the first draft is dropped — see 3.2.)

### 3.9 Before and after

The four-layer skeleton, the dependency direction, every package boundary and
both composition roots are **unchanged**. That is the argument of this
proposal, so it is worth seeing directly: `*` marks every line that moves.

```
BEFORE

  +--------------------------------------------------------------------+
  |  COMPOSITION ROOTS                                                 |
  |                                                                    |
  |    iotsploit-cli  .  iotsploit-django  .  iotsploit-mcp            |
  +--------------------------------------------------------------------+
                                    |
                                    v   depends on
  +--------------------------------------------------------------------+
  |  iotsploit-core                                                    |
  |                                                                    |
  |    domain / ports / services                                       |
  |  * platforms/consts.py            -- 0 call sites                  |
  |    tool_manager                   -- binary resolution             |
  |                                                                    |
  +--------------------------------------------------------------------+
                                    |
                                    v   implemented by
  +--------------------------------------------------------------------+
  |  ADAPTERS                                                          |
  |                                                                    |
  |    platforms . drivers . protocols . exploits . priv               |
  |  * net_audit_mgr._binary()        -- duplicate resolver            |
  |  * no OS probing                  -- nothing asks                  |
  +--------------------------------------------------------------------+
                                    |
                                    v   
  +--------------------------------------------------------------------+
  |  REGISTRY AND EXECUTION                                            |
  |                                                                    |
  |  * import fails  -> dropped, disable_missing()                     |
  |  * no availability concept anywhere                                |
  |  * in the list   =  assumed runnable, on every node                |
  +--------------------------------------------------------------------+


AFTER   (* = the only things that move)

  +--------------------------------------------------------------------+
  |  COMPOSITION ROOTS                                                 |
  |                                                                    |
  |    iotsploit-cli  .  iotsploit-django  .  iotsploit-mcp            |
  +--------------------------------------------------------------------+
                                    |
                                    v   depends on
  +--------------------------------------------------------------------+
  |  iotsploit-core                                                    |
  |                                                                    |
  |    domain / ports / services                                       |
  |  * platforms/consts.py            -- now has callers               |
  |  * capability.py                  -- value + port + tier 1         |
  |  * tool_manager                   -- sole binary resolver          |
  +--------------------------------------------------------------------+
                                    |
                                    v   implemented by
  +--------------------------------------------------------------------+
  |  ADAPTERS                                                          |
  |                                                                    |
  |    platforms . drivers . protocols . exploits . priv               |
  |  * CapabilityResolver             -- tier 2 / tier 3               |
  |  * injected at the two composition roots                           |
  +--------------------------------------------------------------------+
                                    |
                                    v   
  +--------------------------------------------------------------------+
  |  REGISTRY AND EXECUTION                                            |
  |                                                                    |
  |  * import fails  -> kept, carrying the reason                      |
  |  * requirements persisted; availability never is                   |
  |  * execute()     -> re-resolves in the worker process              |
  +--------------------------------------------------------------------+
```

| # | Concern | Today | Proposed |
|---|---------|-------|----------|
| 1 | **OS knowledge** | `consts.py` exists with zero call sites. Nothing anywhere asks whether a capability is present. | `consts.py` gains callers; `capability.py` adds the value type, the resolver port and tier 1. Concrete tiers 2–3 live in an adapter. |
| 2 | **A plugin that cannot load** | Caught, logged at error level, dropped; `disable_missing()` then erases it from the registry. | Kept, carrying the exception as its reason, reconstructed from `EntryPoint.name` and `.value` — neither of which needs the import to have succeeded. |
| 3 | **Where "can I run this" is decided** | Nowhere explicit. Presence in the list is taken as permission, and that list is global. | Resolved per node for display, and **re-resolved in the executor** immediately before running. |
| 4 | **What crosses the persistence boundary** | `PluginMeta` — name, module path, enabled, description. | The same, plus static `requirements`. Availability is deliberately excluded, because it is a fact about one host. |
| 5 | **Binary and path resolution** | `ToolManager`, plus a second `shutil.which` resolver in `net_audit_mgr`, plus 23 device literals and five `/tmp` literals. | One `ToolManager`, one `runtime_dir()`, and VID/PID discovery as the sole owner of port selection. |

Structurally that is five edits to two layers. Everything expensive about this
work is in the count — 22 exploit entry points, 8 drivers, 23 literals, three
operating systems — not in the shape.

## 4. Per-package outcome

| Package | LOC | Linux | macOS | Windows | Note after the work |
|---------|----:|-------|-------|---------|---------------------|
| `iotsploit-core` | 8,476 | full | full | full | Already pure Python. Gains the availability value type, the resolver port, and tier 1. |
| `iotsploit-mcp` | 1,296 | full | full | full | `/tmp/sat_logs` default; computes availability locally over fetched metadata. |
| `iotsploit-django` | 26,328 | full | full | full | SQLite + in-process runtime work everywhere; Redis/Celery already optional. Drops netifaces and smbus2. |
| `iotsploit-cli` | 4,329 | full | full | full | After SIGHUP and process-group fixes. cmd2 and prompt-toolkit are cross-platform. |
| `iotsploit-protocols` | 3,993 | full | partial | partial | SOME/IP and DoIP are plain sockets. SocketCAN enumeration is Linux-only; python-can's other interfaces still work. |
| `iotsploit-drivers` | 4,590 | full | partial | partial | USB needs libusb (brew) or WinUSB via Zadig; udev enumeration blocked; serial ports resolve via VID/PID. |
| `iotsploit-exploits` | 7,905 | full | partial | partial | 8 of 22 fully portable (SSH, SOME/IP, UDS, DoIP, demos); the other 14 blocked on a missing binary, raw sockets, FaceDancer USB, SocketCAN or the privileged helper. |
| `iotsploit-fuzzer` | 3,230 | full | partial | partial | CAN and UART extras portable; the SPI extra stays Linux-only. |
| `iotsploit-platforms` | 1,072 | full | stub | stub | Installs and imports; WiFi methods report NotSupported. Hosts the tier 2/3 resolver. Real netsh/CoreWLAN backends are out of scope. |
| `iotsploit-priv` | 349 | full | by design | by design | Imports cleanly and returns "privileged helper is Linux-only" instead of AttributeError. |

## 5. Delivery

Five phases, each independently shippable, each with a check that proves it.

**Linux regression control.** The first draft claimed later phases "cannot
regress Linux". That was wrong — they change managers, persistence, REST
contracts, process shutdown, hardware defaults and tool execution. The actual
control is: **run the full Linux gate after every phase**, plus focused
hardware-rig validation after Phase 3.

### 5.1 Validation environments

CI proves the packages build and import. Acceptance is proved by running the
real thing on a real box, after the code is complete.

**Windows 11 — VMware guest (primary Windows acceptance target)**

| | |
|---|---|
| Host | `tkxb@192.168.86.128` (`tkxbdewindows`), over SSH |
| Python | 3.10.11 via pyenv-win |
| Poetry | 2.2.1 |
| Virtualenv | `sat-toolkit-S7mkOde6-py3.10`, already created and activated at `C:\Users\tkxb\Projects\iotsploit` |
| Checkout | **Branch `feat/iotfuzzer-django-adapter` @ `16eed71` — the pre-refactor monolithic layout, not the current tree.** See below. |
| Current state | Lockfile consistent; `cryptography`, `SQLAlchemy`, `Django` and `channels` import cleanly — all from that older codebase |

Acceptance run on that box, after implementation:

1. `poetry install` completes from a clean env — the Phase 0 check.
2. Every module imports — the Phase 1 check, run against the real interpreter
   rather than CI's.
3. `iotsploit-cli` starts, reaches a prompt, and `plugin list` renders all 22
   exploits and 8 drivers with a reason on each blocked one.
4. Django starts and serves the plugin listing; the Flutter UI renders the
   blocked state against it.
5. A blocked plugin executed anyway returns the structured error, not a
   traceback — in particular `priv_check`, `can_live_capture` and `wifi_scan`,
   which cover the privileged helper, SocketCAN and the WiFi stub.
6. Ctrl-C and service stop leave no orphaned processes — the Phase 3
   process-group check, which CI cannot prove.

**Reconciled 2026-09-03: that checkout is a different codebase.** Logging in
over SSH shows `C:\Users\tkxb\Projects\iotsploit` sitting on branch
`feat/iotfuzzer-django-adapter` at commit `16eed71`, with the **pre-refactor
monolithic layout** — `sat_toolkit/`, `sat_django_entry/`, `sat_mcp_server/`,
`plugins/devices/...`, `iot_protocol_fuzzer/`, and only `iotsploit-core`
extracted. The current tree's ten `iotsploit-*` packages are not there at all.

That fully explains the working environment: the lockfile is consistent and
`cryptography`/`SQLAlchemy`/`Django`/`channels` import because that older,
simpler dependency set installs cleanly on Windows. It says nothing about
whether the current tree does, and in particular never exercises the mandatory
`iotsploit-platforms` → PyGObject/dbus-python path that section 2.1 identifies
as the Class A blocker.

**So the box is a valid Windows host but not yet a valid test subject.** Before
the six-step run, the current branch has to get there — by pushing it and
checking it out, or by copying the tree into a separate directory so the
existing `feat/iotfuzzer-django-adapter` work is left alone. That is a decision
for the owner, not a mechanical step.

The Poetry-version point still stands:

- The lockfile was generated by **Poetry 2.0.1** (this workspace) and is read
  by **Poetry 2.2.1** (the Windows guest, confirmed 2026-09-03). Both are 2.x on
  `lock-version 2.1`, so they interoperate — but Phase 0's relock must be done
  on one machine with a pinned Poetry version, or the two will churn
  `content-hash` against each other.

**macOS** has no equivalent box yet. Until one exists, macOS is covered by CI
only, and section 4's macOS column is an inference from the dependency and
syscall analysis rather than an observation.

### Phase 0 — Dependency hygiene: make `poetry install` succeed

Mark `pyudev` and the `iotsploit-platforms` GLib/D-Bus dependencies with
`sys_platform == 'linux'`. **Keep `iotsploit-platforms` mandatory at the root**
— making it optional would silently change what a fresh Linux install gets, and
that is a separate decision. Delete `netifaces` (replaced by the psutil already
in the tree), delete the unused `smbus2` declaration, and delete the dead
`tools/third_party/INA219.py` that imports an undeclared `smbus`. One relock,
done alone so the `poetry.lock` diff stays reviewable.

- **Exit:** install succeeds on all three OSes, and the Linux lock delta matches
  a stated expectation — `netifaces` and `smbus2` removed, the GLib/D-Bus chain
  unchanged on Linux, nothing else moved. (Byte identity is impossible once a
  dependency is deleted; the first draft's exit criterion contradicted its own
  scope.)
- **Cost:** ~1.5 days · 6 pyproject files, 3 call sites, 2 deletions.

### Phase 1 — Import safety: every module imports everywhere

Move `pwd`/`grp` inside the Linux branch of `priv/native.py`; guard `AF_UNIX` in
`priv/client.py` so it raises the designed `PrivilegedHelperUnavailable`; make
`drv_ft2232` import pyudev lazily; register only the signals that exist; add a
`null` platform adapter. Guard the Linux-only tests at module scope
(`test_native.py`, `test_client.py`, `test_daemon.py` use `AF_UNIX`,
`socketpair`, `/bin/sleep` and `os.getuid()`, and are all marked
`pytest.mark.unit` — the marker the Windows matrix runs) so collection succeeds.

- **Exit:** a smoke test that imports every module in every package, run on all
  three OSes; and `pytest -m unit` collects cleanly on Windows.
- **Cost:** ~2.5 days · 5 source files, 3 test files.

### Phase 2 — Requirements, resolver, and per-node availability

The core value type, resolver port and tier 1; the tier 2 resolver adapter in
`iotsploit-platforms` wired at both composition roots; `REQUIRES` on the 22
exploit entry points; the failed-import path built from `EntryPoint.name` /
`.value`; `requirements` (not availability) persisted through `PluginMeta`; the
separate driver availability record and its API path; the executor-side
re-resolve; and blocked-state rendering in the Flutter UI.

- **Exit:** on Windows the CLI and Django both start, and the listing shows all
  22 exploits and 8 drivers with a reason on each blocked one. A Linux Django
  dispatching to a Windows worker gets the worker's answer, not its own.
- **Cost:** ~7 days · 1 new core module, 1 new adapter, ~16 files touched.

### Phase 3 — Paths, processes and external tools

The `runtime_dir()` owner replacing the `/tmp` paths; the 23 device literals
routed through existing VID/PID discovery; a process-group helper that degrades
to `terminate()`; a thread-based pipe reader for Ubertooth; the four binary call
sites and `net_audit_mgr._binary()` consolidated onto the existing ToolManager;
CPU temperature via psutil; `LinuxCommands` registered only where it applies.

- **Exit:** no literal `/tmp`, `/dev/tty`, `/sys` or bare binary name outside an
  adapter, enforced by a ruff rule or grep test; **plus a hardware-rig pass** —
  device scan, a CAN capture and a serial read on real hardware, because this is
  the phase that touches device defaults.
- **Cost:** ~4 days · widest diff.

### Phase 4 — CI matrix that actually proves the goal

Add a GitHub Actions matrix over ubuntu/macos/windows running the `unit` and
`contract` markers, with `hardware` and `service` excluded, and the **full Linux
gate on every phase**.

Two things the first draft got wrong:

- **Keep `tools/testing/test-python-full.sh`.** It is the contract referenced by
  `AGENTS.md` and executed directly by `tools/git-hooks/pre-commit:15`. If a
  Python runner is introduced for Windows, the shell script becomes a thin
  wrapper around it — it does not disappear.
- **A root workspace install proves nothing about per-package installability.**
  `poetry install` at the root resolves every path dependency together and will
  happily mask a missing declaration in a standalone package. If "every package
  installs" is the acceptance criterion, the matrix must **build each wheel and
  install it into a clean environment** on each OS.

- **Exit:** a red CI on Windows is what stops the next Linux-only import from
  landing, and a red per-wheel job is what stops the next missing declaration.
  Final sign-off is the six-step acceptance run on the Windows 11 guest in 5.1,
  not a green CI badge.
- **Cost:** ~3 days.

**Total: about 18 engineering days.** Phases 0 and 1 (4 days) still get the
project to "installs and starts on Windows and macOS" — everything after that is
the correctness of the explanation and the proof that it holds.

## 6. Explicit non-goals

- **SocketCAN on Windows.** Not possible; python-can's PCAN, Vector, Kvaser and
  virtual interfaces are the answer, and the protocol code above the interface
  is already agnostic. The capability simply reports it.
- **Real WiFi backends for macOS and Windows.** CoreWLAN and netsh WLAN are each
  a project of their own. The stubs stay stubs and say so.
- **A Windows privileged helper.** `iotsploit-priv` is a deliberate, audited
  privilege boundary built on systemd socket activation and unix credentials.
  Reimplementing it on a service-and-named-pipe model would need its own
  security review and is not in this scope. See
  `docs/exec-plans/active/privileged_execution_plan.md`.
- **Making `iotsploit-platforms` optional on Linux.** Deliberately deferred; it
  would change the default Linux feature set.
- **The Flutter UI.** Already cross-platform; the only change is rendering the
  blocked state.

## 7. Risks

| Risk | Mitigation |
|------|------------|
| **Availability leaks into persistence.** The easiest wrong move is caching an `Availability` on `PluginMeta` "just for the UI", which silently breaks every multi-node deployment. | Keep availability off the persisted model entirely, and keep `HttpPluginMetaRepository.upsert()` a no-op. A test asserts the serialized `PluginMeta` carries `requirements` and no availability field. |
| **Tier confusion.** A tier-3 check (open the device) drifting into a tier-1 or tier-2 path claims exclusive hardware or prompts during a plain listing. | Tiers are separate functions with separate call sites; listing paths never call the tier-3 resolver. Hot-plug correctness follows from tier 3 not being cached. |
| **Lock-file churn.** Adding environment markers relocks everything. | Do it alone in Phase 0 and review against a stated expected delta. |
| **CI that passes while the goal is unmet.** Root-install CI hides per-package dependency gaps; marker filters hide collection failures. | Per-wheel clean installs, and an import smoke test that runs before marker selection. |
| **Scope creep into feature parity.** The tempting next step is implementing the Windows backends. | The non-goals exist to make that a separate decision. |

## 8. Open questions for the decision owner

1. Should a blocked plugin be **hidden by default** in the UI with a "show
   unavailable" toggle, or always listed? This proposal assumes always listed.
2. For the distributed runtime, should the dispatcher **pre-filter** on its own
   node's availability as a UX nicety (fast feedback, occasionally wrong), or
   only ever report the worker's answer (always right, one round trip)?
3. Is a Windows/macOS developer machine actually in scope, or only a
   **Windows/macOS operator console** driving a Linux rig over HTTP? The second
   is considerably cheaper and may make Phase 3 unnecessary.

## 9. What changed in this revision

| # | Review finding | Resolution |
|---|----------------|------------|
| 1 | Availability is node-specific but was routed through global persistence. | New 3.3. Only `requirements` persists; availability is computed per node and never stored; the final gate moves into the executor. Confirmed `HttpPluginMetaRepository.upsert()` is already a deliberate no-op. |
| 2 | `REQUIRES` is unreachable when `entry_point.load()` fails. | New 3.4. Two discovery paths; the failed-import path uses `EntryPoint.name`/`.value` and the exception itself as the reason — no declaration needed, no new metadata channel. |
| 3 | Concrete probing in core violates the dependency rule; core has no pyserial. | New 3.2. Core keeps the value type, the resolver port and stdlib-only tier 1. Tiers 2–3 move to `iotsploit-platforms`, injected at the existing composition roots. `default_serial_port()` dropped. |
| 4 | Process-lifetime caching plus "open the device" probes are unsafe and stale. | New 3.1. Three tiers with distinct lifetimes; tier 3 never runs during listing and is never cached; VID/PID discovery stays the owner of port selection. |
| 5 | Phase 0's "byte-identical" exit contradicted its own scope. | `iotsploit-platforms` stays mandatory; exit is a *stated lock delta*. Bonus: `smbus2` is unused and `INA219.py` is dead code importing an undeclared `smbus` — both deleted rather than marked. |
| 6 | CI did not prove the stated goal. | Phase 4 rewritten: per-wheel clean installs, the `.sh` gate preserved as the contract and wrapper, Linux-only tests guarded at module scope (they are marked `unit`, the marker the matrix runs), full Linux gate after every phase, hardware-rig pass after Phase 3. The "cannot regress Linux" claim is withdrawn. |

Effort moved from ~12 to ~18 days, almost entirely in Phase 2 (per-node
evaluation and the separate driver model) and Phase 4 (real install proof).

## 10. Implementation status

Verified on Linux at the time of writing: `tools/testing/test-python-full.sh`
passes (ruff clean, import smoke clean, portability literals clean, **1245
passed / 5 skipped**), and `ui/tools/testing/test-flutter-full.sh` passes
(**518 passed**, analyze clean).

| Phase | State | Evidence |
|-------|-------|----------|
| **0 — dependency hygiene** | done | `PyGObject`/`dbus-python` carry `sys_platform == 'linux'`; `netifaces` replaced by `psutil` and removed; `smbus2` and the dead `INA219.py` deleted; `pyudev` gone entirely (it survives only as a hint string). |
| **1 — import safety** | done | `pwd`/`grp` and `AF_UNIX` guarded; `drv_ft2232` imports pyudev lazily; the CLI registers only signals that exist on the platform; `null` WiFi adapter added; the Linux-only priv tests are guarded at module scope. `tools/testing/import-all-packages.py` imports every module in all ten packages. |
| **2 — requirements and per-node availability** | done | `iotsploit_core/platforms/capability.py` holds `Availability`, the `CapabilityResolver` port and stdlib-only `static_compatibility`; `PlatformCapabilityResolver` implements tiers 2–3 in `iotsploit-platforms`; all 22 exploit entry points and all 8 drivers declare `REQUIRES`; `PluginMeta.requirements` persists via migration `0004`; both managers gate execution and re-resolve at the executor; REST exposes availability for plugins (`list_plugin_info`) and drivers (`list_driver_info`). |
| **2 — UI blocked state** | done | `plugins_page.dart` (card, mobile card, table row), `control_center_screen.dart` (`_loadable` extended — the single gate the Execute button reads), and `devices_page.dart` (driver banner and table badge). Every Execute path is disabled with the reason in a tooltip rather than hidden. |
| **3 — paths, processes, tools** | done | `runtime_dir()`/`log_dir()` own the former `/tmp` literals; **zero** `/dev/ttyUSB*` or `/dev/ttyACM*` literals remain; process-group handling lives in one helper that degrades to `terminate()` off POSIX; the Ubertooth `select.select` on a pipe is gone; `LinuxCommands` is skipped at module discovery on non-Linux. Enforced by `tools/testing/check-portability-literals.py`. |
| **4 — CI and the gate** | done, wheel check verified | `.github/workflows/cross-platform.yml` runs an ubuntu/macos/windows matrix plus a Linux full-gate job. `tools/testing/run_gate.py` owns the step list and runs on all three platforms; `test-python-full.sh` is now a thin wrapper around it, so `AGENTS.md` and `tools/git-hooks/pre-commit` keep working unchanged. Per-wheel clean installs run in CI only; executed locally on 2026-09-03 and **all ten packages build, install standalone and import** (it also used to leak a wheelhouse plus one venv per package per run — 4.4 GB had accumulated — now scoped to one auto-cleaned workspace). |
| **5.1 — Windows acceptance** | **blocked** | The guest is reachable and correctly provisioned (Win 11 26200, Python 3.10.11, Poetry 2.2.1), but its checkout is a *different, pre-refactor codebase* (section 5.1). The current branch has to reach the box first — a decision for the owner. |
| **macOS** | **no box** | Covered by CI only; the macOS column in section 4 remains an inference. |

Two guards worth knowing about, because they are what stop the design eroding:

- `iotsploit-django/tests/test_plugin_requirements_persistence.py` fails if an
  availability-shaped field ever appears on `PluginMeta` or the `Plugin` model.
  That is the invariant the whole multi-node design rests on (section 3.3).
- `check-portability-literals.py` fails on a new `/tmp`, `/dev/tty` or `/sys`
  literal outside the three adapters that legitimately own one.

Nothing is committed. The work sits in the `dev` working tree.

## 11. Companion artifact

A rendered version of this proposal is published at:

https://claude.ai/code/artifact/50ecb5af-9dd0-4932-bbeb-46c04291679d
