# Privileged Execution Boundary Plan

## Status

- **State:** A1 complete; paused before A2
- **Original decision date:** 2026-09-02
- **Review date:** 2026-09-02
- **Selected boundary:** A root-owned verb daemon on a Unix socket, plus
  `CAP_NET_RAW` only for workers that send raw packets
- **Decision owner:** User
- **Estimated effort:** 8–12 engineering days
- **Implementation branch:** `security/privileged-execution-boundary`

The first draft was not implementation-ready. This revision removes the false
claim that an application-side confirmation prompt is a root boundary, removes
`NET_ADMIN` from application workers, replaces the argv-shaped client with a
verb-shaped contract, inventories the live host-state operations, separates
systemd and container deployment, bounds daemon resources, and puts the new
tests inside the repository's collected test paths.

## Governing Standards

- `AGENTS.md` — **Delete > Replace > Add.** Unused privileged paths are
  deleted instead of receiving new verbs.
- `AGENTS.md` — **Solve at the owner.** User-supplied scan ranges are validated
  by `ip_scan.parse_hosts`; the root daemon independently validates every
  privileged argument because the application is its caller, not its trust
  anchor.
- `AGENTS.md` — MCP and direct Django listeners remain on loopback. Nginx is
  the only published HTTP listener.
- `docs/architecture.md` — core defines no operating-system implementation.
  The socket client is a small outer-ring package used by Django and drivers;
  the root daemon imports no application code.
- `.agents/standards/testing.md` and `tools/testing/test-python-full.sh` apply.

## Objective and Success Criteria

Make the root surface finite and make the mutating network surface
authenticated.

When this plan is complete:

1. No application process executes `sudo`, a shell containing privileged
   commands, or an application-controlled Python module as root.
2. The root daemon accepts exactly four host-state verbs and constructs every
   argv itself from validated values.
3. Django and Celery workers never receive `CAP_NET_ADMIN`. Workers that need
   raw sockets receive only `CAP_NET_RAW`.
4. Every mutating `/api/` request requires the configured bearer token, and
   Daphne is reachable only through loopback nginx proxying.
5. Uploaded files and caller-supplied plugin metadata cannot become importable
   plugins.
6. Existing live CAN, DoIP, routed IP-scan, nmap sweep, and flood-plugin paths
   either work through their new owner or fail with a clear unavailable error.
7. The full Python gate collects and passes the daemon, client, auth, loader,
   validation, and owner migration tests.

## Threat Model

### Untrusted

- HTTP, WebSocket, and MCP callers
- Uploaded file contents and filenames
- Plugin parameters, targets, interface names, networks, addresses, and ports
- Environment variables inherited from the service account
- Data read from the application database

### Trusted for this plan

- Root-owned installed daemon and unit files
- Installed application and plugin code running as the service account
- The operator who installs the helper and provisions the API token

Installed plugins remain trusted service-account code, matching the existing
plugin model. Compromise of the service account is **not** claimed to require a
second browser confirmation: any process with the service account's membership
in the `iotsploit` group can call the four daemon verbs. The security property
after such a compromise is containment to those verbs, not denial of all host
changes.

An application confirmation prompt may be designed later as an operational
safety feature. It is not part of this privilege boundary, because code running
as the service account could connect to the socket directly and bypass it.

## Non-goals

- Sandboxing installed plugins from one another
- Multi-user authorization, RBAC, or per-MCP-node identities
- A browser confirmation workflow for host-state changes
- Rewriting the plugin lifecycle, test-step engine, or Celery lifecycle
- Windows support
- Host-state changes from distributed worker containers; those workers fail
  closed because a daemon in another network namespace would modify the wrong
  namespace

## Current State

Verified against `dev` on 2026-09-02. The baseline gate passes: Ruff clean,
1,105 tests passed, 5 skipped, and 42 warnings.

### Remote chains to root

1. `/upload_file/` accepts Python, `/exploits/discovered/` stores a supplied
   `module_path` enabled, and `/execute_plugin/` hands a `RequiresRoot` plugin
   to `sudo -E <python> -m plugin_sudo_runner`.
2. `ip_scan` accepts `hosts`, `parse_hosts` only splits it, and
   `NetAudit_Mgr.ip_detect` interpolates it into a root shell command. For
   example, `parse_hosts("127.0.0.1; id")` currently returns
   `["127.0.0.1;", "id"]`.

`sudo -E` is not a boundary: the service account controls Python import paths,
plugin files, database metadata, and environment variables consumed by the
root interpreter.

### Privileged inventory and disposition

| Owner | Current operation | Disposition |
|---|---|---|
| `tools/privilege_mgr.py`, `plugin_sudo_runner.py` | Arbitrary plugin under root Python | Delete |
| `tools/apt_mgr.py` | `sudo apt-get install/remove`; no repository callers | Delete |
| `tools/bluetooth_mgr.py` | Root Bluetooth scan/configuration; no repository callers | Delete with now-unused `bluepy` dependency |
| `NetAudit_Mgr.modify_route` | Root route mutation; no repository callers | Delete |
| `NetAudit_Mgr.ip_detect`, `port_detect` | nmap sweep/connect scan | Worker argv; no root daemon |
| `NetAudit_Mgr` flood methods | ping/macof/hping3 background processes | Worker argv with owned PIDs |
| `IPScanPlugin._add_routes/_del_routes` | Add/delete routes through gateway | `route-via` daemon verb |
| `DoIP_Mgr.connect` | Set fixed link-local address and route | `doip-config` daemon verb |
| `SocketCANDriver` | Configure, raise, cycle, and lower CAN links | `can-up` and `can-link-state` daemon verbs |
| `PCANDriver` | Configure a PEAK adapter for CAN FD, raise and lower it | `can-fd-up` and `can-link-state` daemon verbs |
| `syn_flood_attack` | Scapy layer-3 packets | Worker `CAP_NET_RAW`; delete `RequiresRoot` |

Before deleting a file, repeat the repository reference and entry-point search
on the implementation branch. A discovered live caller stops deletion and
requires a plan amendment; it does not silently gain a generic root verb.

### Deployment facts

- Daphne currently listens on `0.0.0.0:8888` and `:9999`; Compose publishes
  both ports.
- Daphne runs as `www-data`; supervisor and nginx run as root.
- `docker/start.sh` creates `admin/admin123` on fresh storage.
- `settings/prod.py` inherits `DEBUG=True`, `ALLOWED_HOSTS=["*"]`, permissive
  CORS, and the development secret.
- The image contains neither systemd nor nmap and is managed by supervisor.
  A systemd installer cannot be reused as the container service manager.

## Architecture Decision

### Boundary alternatives

| Criteria | Password prompt | Setuid helper | Root verb daemon |
|---|---|---|---|
| Root action bounded by code | No | Yes | Yes |
| Works without TTY | No | Yes | Yes |
| Compatible with worker `NoNewPrivileges` | n/a | No | Yes |
| Python implementation safe | n/a | No | Yes, if root-owned and stdlib-only |
| Container service-manager fit | Poor | Medium | Good with supervisor-specific launch |
| Selected | No | No | **Yes** |

### Authorization boundary

There are two distinct controls:

- **Network authorization:** one required bearer-token check in Django
  middleware for unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) under
  `/api/`. The expected token comes from `IOTSPLOIT_DJANGO_API_TOKEN`, is
  compared with `secrets.compare_digest`, is never logged, and is mandatory in
  production settings. MCP already forwards this environment variable. The UI
  must supply the same token before the deployment acceptance test can pass.
- **Root authorization:** filesystem access to
  `/run/iotsploit/priv.sock`, mode `0660 root:iotsploit`. Membership in
  `iotsploit` is the grant. `SO_PEERCRED` records the caller UID for audit, but
  it does not pretend to recover the HTTP identity.

The middleware is placed at the `/api/` owner instead of decorating dozens of
views. Read-only methods remain reachable for compatibility. Production fails
startup when the token, secret key, allowed hosts, or allowed CORS origins are
missing.

### Client contract and package boundary

Create one outer-ring package:

```text
iotsploit-priv/
  pyproject.toml
  src/iotsploit_priv/client.py
  privd/iotsploit-privd
  systemd/iotsploit-privd.socket
  systemd/iotsploit-privd.service
  tests/
```

`iotsploit_priv.client.call(verb, args, timeout=...)` speaks the JSON socket
protocol. It never accepts argv, never falls back to sudo, and never imports or
executes the daemon. `iotsploit-django` and `iotsploit-drivers` depend on this
outer-ring package. `iotsploit-core` remains unchanged.

The daemon is a separate root-owned, standard-library-only program. It does
not import `iotsploit_priv`, the application venv, or any application module.
Sharing the directory is source organization, not a runtime dependency.

## Phase 0 — Close the Remote Paths

Phase 0 is independently releasable and precedes helper work.

### A1 — Authenticate and bind locally

The GET/HEAD audit found five hardware actions exposed as GET: scan all,
scan one driver, scan-and-list, initialize, and cleanup. They move to POST.
`device_info` also changed `SAT_RUN_IN_SHELL`; web mode now defaults at
`Env_Mgr`, the process-mode owner, so the information route is read-only.

Completed on 2026-09-02 on `security/privileged-execution-boundary`:

- one middleware now fails closed on every unsafe `/api/` method and compares
  the configured bearer token with `secrets.compare_digest`;
- production requires its secret, hosts, origins, and API token, while forcing
  debug and permissive CORS off;
- CLI and container Daphne listeners bind to loopback, Compose publishes only
  nginx port 80, and the image advertises only port 80;
- the built-in administrator and password were deleted, and deployment/MCP
  documentation now describes explicit token provisioning;
- focused contracts passed (22 initially, then 30 with the authenticated
  interaction contracts), Compose configuration validation passed, and the
  full gate passed with 1,124 tests passed, 5 skipped, and 42 warnings.

- Add one API middleware enforcing the bearer token on unsafe `/api/` methods.
- Audit all GET/HEAD routes once; any route with a side effect moves to an
  unsafe method before method-based middleware is treated as the boundary.
- Add contract tests covering missing, wrong, and correct tokens and confirming
  that GET behavior is unchanged.
- Bind Daphne to `127.0.0.1`; remove direct Compose publication of 8888/9999.
- Make `prod.py` set `DEBUG=False`, require `SECRET_KEY`, parse explicit
  `ALLOWED_HOSTS` and CORS origins, and fail closed when absent.
- Delete built-in `admin/admin123` provisioning. Token creation is deployment
  configuration, not an account generated into logs.
- Update MCP and deployment documentation to require
  `IOTSPLOIT_DJANGO_API_TOKEN`. The separate UI must support supplying it.

### A2 — Delete caller-controlled plugin registration

- Delete the `/exploits/discovered/` route, view, endpoint-specific imports,
  and tests. Keep the manager's internal metadata upsert used by trusted local
  discovery. There is no compatibility branch that accepts caller paths.
- Harden filesystem plugin loading with `Path.resolve()` and
  `relative_to(plugins_dir.resolve())`; reject symlinks or database metadata
  escaping that root.
- Keep the generic upload feature unchanged except for authentication. Once the
  registration path and loader escape are gone, uploaded files are data and
  cannot become plugins. Content-type policy belongs to the upload consumers,
  not this privilege plan.

### A3 — Remove shell interpretation

- `ip_scan.parse_hosts` accepts only IPv4 host/CIDR values parseable by
  `ipaddress.ip_network(..., strict=False)`, rejects more than 256 entries, and
  rejects any single network larger than 65,536 addresses. These limits retain
  the existing `/16` scans and reject unbounded `/0` work.
- Convert nmap, ping, macof, hping3, and temporary host-state commands to argv
  execution. During Phase 0, a host-state command may retain explicit
  `sudo -n` as an argv element; no shared generic privileged runner is created.
- `nmap -sn` runs in the worker with `--privileged` when the worker has
  `CAP_NET_RAW`; `nmap -sT` runs unprivileged. Hosts and port specifications are
  validated before argv construction.
- Background jobs use `Popen(..., stdin=DEVNULL, stdout=DEVNULL,
  stderr=DEVNULL, start_new_session=True)`. Store each returned process in the
  existing manager and terminate only processes that manager started. Delete
  every `pkill` path.
- Delete the unused apt, Bluetooth, and route-mutation paths listed above.

Phase 0 ends with no user-controlled value on an inventoried privileged path
entering a shell command and no unauthenticated mutating API request. The
legacy test-step engine remains only for operator-authored scripts.

## Phase 1 — Privileged Helper

### Complete initial vocabulary

| Verb | Arguments | Fixed operation |
|---|---|---|
| `can-up` | `iface`, `bitrate` (integer or null) | Configure a physical CAN bitrate when supplied, then raise the CAN/vCAN link |
| `can-fd-up` | `iface`, `bitrate`, `sample_point`, `dbitrate`, `dsample_point` | Lower a physical CAN link, configure it for CAN FD with both bit timings, then raise it |
| `can-link-state` | `iface`, `state` (`up`/`down`) | Raise or lower an owned CAN link |
| `doip-config` | `iface` | Replace `169.254.58.58/16` and route `169.254.0.0/16` on the interface |
| `route-via` | `action` (`add`/`delete`), `cidr`, `gateway` | Add or delete one IPv4 route through a gateway |

There is no `sweep` verb: nmap does not change host state. There is no generic
`link-state`, arbitrary address, arbitrary executable, apt, or Bluetooth verb.

Daemon validation rejects unknown verbs, unknown/missing/duplicate argument
keys, wrong JSON types, NULs, and values outside these rules:

- CAN interface: `^(v?can)[0-9]{1,3}$`
- General interface: `^[a-z0-9._-]{1,15}$`
- Bitrate: physical `canN` requires an integer from 10,000 through 10,000,000;
  `vcanN` requires null and skips configuration
- Sample point: a number from 0.5 through 0.95, formatted to three decimals;
  `can-fd-up` rejects `vcanN`, which has no bit timing
- Network and gateway: IPv4 only; route network at most 65,536 addresses
- State/action: exact enumerated strings

The caller also validates at its input boundary for useful errors. Daemon
validation remains authoritative.

### Wire and resource contract

- One request per connection:
  `{"verb":"...","args":{...}}\n`
- Maximum request: 4 KiB, including the newline. EOF before newline, oversized
  input, trailing bytes, arrays, and duplicate JSON keys are rejected.
- One response:
  `{"ok":bool,"exit":int,"stdout":str,"stderr":str}\n`
- Capture at most 8 KiB each from stdout and stderr. After JSON escaping,
  truncate fields again as needed so the encoded response never exceeds
  24 KiB; include `output_truncated: true` when truncation occurred.
- Per-verb timeout: 10 seconds. On timeout the process group is terminated and
  then killed after one second.
- `stdin=DEVNULL`, `close_fds=True`, `start_new_session=True`, `env={}`.
- Absolute executable paths only. The verb table creates argv; client argv is
  never accepted.
- Requests are handled serially in v1 and the socket backlog is 16. These
  commands are short; concurrency adds state races without a demonstrated
  need.
- A structured audit record is written to stderr/journald before execution and
  after completion, containing timestamp, peer UID/PID, verb, validated args,
  exit status, and duration. It never records environment or bearer tokens.

### Native installation

| Path | Owner/mode | Purpose |
|---|---|---|
| `/usr/local/libexec/iotsploit-privd` | `root:root 0755` | Daemon |
| `/etc/systemd/system/iotsploit-privd.socket` | `root:root 0644` | Socket ownership and activation |
| `/etc/systemd/system/iotsploit-privd.service` | `root:root 0644` | Capability and filesystem bounds |
| `/run/iotsploit/priv.sock` | `root:iotsploit 0660` | Client boundary |

The socket unit owns `/run/iotsploit/priv.sock`; the daemon consumes the
systemd-provided listening fd after validating `LISTEN_PID` and `LISTEN_FDS`.
The service has only `CAP_NET_ADMIN` in its capability bounding set, plus
`NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`,
`PrivateTmp=yes`, and address families `AF_UNIX AF_NETLINK`.

Native Django/Celery worker units receive only:

```ini
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
NoNewPrivileges=yes
```

`sudo` is used only by the interactive native installer. The installed daemon,
units, and their parent directories must be root-owned and not writable by the
service account. The installer creates the `iotsploit` system group, validates
an explicit `--service-user` (default `www-data`) through the system account
database, adds that account to the group, and tells the operator which service
processes must restart before the membership takes effect.

### Owner migrations

- SocketCAN calls `can-up` and `can-link-state` directly through the client.
- PCAN calls `can-fd-up`, whose three commands set the per-verb worst case the
  client timeout must outlast.
- DoIP calls `doip-config` before connecting.
- IP scan calls `route-via` with `add` for each route and records only routes
  it successfully added. An existing route makes `add` fail and is never
  recorded, so cleanup cannot delete state the scan did not create.
- Missing/unhealthy helper returns a typed unavailable error. Each owner turns
  that into its existing public error/result shape with the install hint.
- No fallback to sudo or shell execution exists after an owner migrates.

When the last caller migrates, delete `privilege_mgr.py`,
`plugin_sudo_runner.py`, the `RequiresRoot` branch and flag, the `elevate`
dependency, and sudo-runner-specific tests/comments in the same change.

## Phase 2 — Container Deployment

The container does not run systemd and does not call the native installer.
The Docker build copies the same daemon bytes to the same root-owned libexec
path and supervisor starts it in local mode.

- Keep the container entry process as root; `docker/start.sh`, nginx, and
  supervisor require it. Do not set the entire Compose service to `www-data`.
- Install `iproute2`, nmap, and the capability-launch tool used by supervisor.
- Compose drops all capabilities, then adds only `NET_ADMIN`, `NET_RAW`, and
  `NET_BIND_SERVICE` to the container bounding set.
- Supervisor launches each child through a root-owned `setpriv` wrapper that
  narrows its permitted/effective/ambient/bounding sets:
  - daemon: `NET_ADMIN`
  - Daphne: `NET_RAW`, then UID/GID `www-data`
  - nginx: `NET_BIND_SERVICE`, then UID/GID `www-data`
- The wrapper sets `no_new_privs` after establishing the child's final UID and
  capabilities. Tests inspect `/proc/<pid>/status` to verify effective,
  permitted, ambient, and bounding sets; configuration text alone is not
  evidence.
- Nginx uses service-account-owned log, pid, and temporary directories so it
  never needs `SETUID`, `SETGID`, `CHOWN`, or filesystem-override capabilities.
- Without systemd socket activation, the daemon creates the container socket,
  resolves the `iotsploit` group, applies `0660 root:iotsploit` before listen,
  and only replaces a stale path after verifying it is a root-owned socket.
- The socket remains `0660 root:iotsploit`; `www-data` is a member.

Only the single-container local runtime supports host-state verbs. Distributed
Celery containers may receive `NET_RAW` for raw-packet plugins but do not mount
the privileged socket and return the unavailable error for CAN, DoIP network
configuration, or routed scan setup. A helper in another container would
modify a different network namespace and is therefore forbidden.

## CLI Surface

The native CLI adds:

```text
priv status
priv install
priv uninstall
priv verbs
```

- `priv install` prints exact sources, destinations, modes, verb hash, and
  checksum before an explicit y/N, then invokes the packaged native installer
  with `sudo` on the terminal. It never reads or pipes a password.
- `priv uninstall` is equally explicit and removes the socket unit, service
  unit, daemon, and empty runtime directory.
- `priv status` returns 0 healthy, 1 absent, or 2 installed-but-broken. It
  checks ownership, every parent directory's writability, socket mode/group,
  service-account membership, daemon response, and verb-table hash.
- The container image does not expose install/uninstall; its files are image
  contents managed by the Docker build.

## Verification

### Collected deterministic tests

Add `iotsploit-priv/tests` to root `pyproject.toml` `testpaths`. Tests cover:

- every verb's valid argv and validation boundaries
- malformed, duplicate-key, oversized, trailing, and partial requests
- timeout/process-group cleanup and output caps with harmless fake executables
- peer audit fields and exact response schema
- client absent/refused/timeout/protocol-error behavior
- API middleware for missing, wrong, and correct bearer tokens
- plugin-loader containment including `..` and symlink escapes
- `parse_hosts` injection, type, count, IPv4, and network-size boundaries
- background-process ownership: stopping one manager never signals unrelated
  processes
- CAN, DoIP, and route owners issuing the exact verb/args and mapping helper
  unavailability into their public error shape

Tests use temporary sockets and fake executables and require neither root,
hardware, real network changes, nor systemd.

### Static invariants

These searches must return no runtime hits outside installer text or
user-facing instructions:

```bash
rg -n --glob '*.py' '\bsudo\b|RequiresRoot|elevate' iotsploit-*
rg -n --glob '*.py' 'exec_cmd\(.*(nmap|ping|macof|hping3|ip |ifconfig|hciconfig)' .
rg -n 'admin123|interface=0\.0\.0\.0|8888:8888|9999:9999' docker docker-compose.yml
```

Also verify imports: core must not import `iotsploit_priv`, Django, drivers, or
platform code.

### Native rig

1. `priv status` reports absent with exit 1 on a clean rig; raw-only scans still
   work and host-state owners fail with the install hint.
2. Install, verify root ownership/modes and `systemd-analyze verify` both units,
   then confirm `priv status` returns 0.
3. Exercise every verb against disposable CAN/link/network fixtures and verify
   exact before/after state and cleanup.
4. Send invalid interface, bitrate, IPv6, `/0`, unknown verb, extra key, 4-KiB
   overflow, and partial requests; none executes a child.
5. Confirm the daemon process has `CAP_NET_ADMIN` but not `CAP_NET_RAW`, and the
   worker has `CAP_NET_RAW` but not `CAP_NET_ADMIN`.
6. Run `syn_flood_attack` and nmap sweep with no sudo process and no root Python
   importing application code.
7. Make the installed daemon or a parent directory group-writable;
   `priv status` returns 2.

### Container

1. Build from the checked-out tree, not a fresh network clone, then run local
   mode.
2. Confirm only port 80 is published and direct 8888/9999 connections fail.
3. Confirm missing/wrong bearer tokens receive 401 on mutating APIs and the
   correct token succeeds.
4. Inspect child capability sets: Daphne has only `NET_RAW`, privd only
   `NET_ADMIN`, nginx only `NET_BIND_SERVICE`.
5. Exercise the same disposable network fixtures inside the local container.
6. Start the distributed profile and confirm workers have no privileged socket
   and host-state operations fail closed.

Run `tools/testing/test-python-full.sh` before every commit containing Python.
Report passed, failed, skipped, and warning counts. Hardware/network-namespace
checks are reported separately and are never hidden behind skipped unit tests.

## Sequencing

| Step | Depends on | Estimate |
|---|---|---:|
| A1 — API auth, production settings, listener containment | — | 1.5–2 d |
| A2 — delete registration, contain loader | — | 0.5–1 d |
| A3 — argv conversion, validation, PID ownership, dead deletion | — | 1.5–2 d |
| Helper/client package, systemd units, pure tests | A3 inventory | 2–3 d |
| CAN/DoIP/route migration and privileged-runner deletion | Helper | 1.5–2 d |
| Container supervisor/capability deployment | Helper | 1–2 d |
| Native CLI and rig verification | Helper | 1–1.5 d |

Land A1 first because it collapses the remote unauthenticated surface. A2 and
A3 may follow independently. Build the helper only from the post-deletion live
inventory; migrate one owner at a time with no fallback. Delete the arbitrary
root runner as soon as the raw-packet plugin and all live host-state owners have
migrated.

## Implementation Approval Gate

Approval of this document authorizes creation of
`security/privileged-execution-boundary` from the current `dev` commit while
preserving the user's existing documentation changes. Implementation then
starts with A1 and must stop rather than weakening auth, validation, capability,
or test requirements to make a phase pass.
