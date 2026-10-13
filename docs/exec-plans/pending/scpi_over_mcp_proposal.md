# SCPI over MCP Proposal

## Status

- **State:** Proposal, not started
- **Draft date:** 2026-10-13
- **Basis:** SCPI already runs end-to-end on the rig
  (`iotsploit-drivers/.../esp32/scpi_client.py` → `drv_esp32._command_impl` →
  Django `execute_device_command`). The only gap is that `iotsploit-mcp` does
  not surface the device-command endpoints, so an AI agent can see devices but
  cannot issue a driver command (SCPI or otherwise) against one.
- **Estimated effort:** Phase 1 ~0.5 day. Phase 2 is a separate decision, not
  estimated here.
- **Decision owner:** User
- **Blocked on:** nothing for Phase 1.

**Goal.** Let an external AI agent drive the SCPI-backed device commands that
already exist, through MCP, without adding a parallel SCPI path and without
widening the mutating surface beyond what Django already gates.

## Governing Standards

- `AGENTS.md` — **Delete > Replace > Add**, **Search and reuse first**,
  **Keep scope minimal.** The SCPI stack, the driver command map, and the
  Django endpoints already exist. This proposal adds adapter tools only; it
  builds no new SCPI machinery.
- `iotsploit-mcp/README.md` — owns the MCP tool surface and the rule that a
  mutating tool goes through Django's configured bearer token while the MCP
  endpoint itself stays bound to loopback. New mutating tools follow that rule.
- `docs/architecture.md` — ports-and-adapters. MCP is an adapter over the
  Django HTTP API; it must not reach hardware directly.

## 1. What exists today

SCPI is not missing from IoTSploit — it is missing only from the agent surface.

1. **Transport + client** — `esp32/scpi_client.py` provides `ScpiClient`
   (`send_command`, `query`, `reset`, `get_status`, `get_version`) over two
   ready transports: `ScpiTcpTransport` (socket, e.g. port 5025) and
   `ScpiSerialTransport` (pyserial).
2. **Driver** — `drv_esp32.py` owns a named-command vocabulary
   (`scan_wifi`, `get_version`, `reset`, `flash_firmware`, `erase_flash`,
   `get_chip_info`, …) in `_command_impl`, each issuing SCPI under the hood
   (`WIFi:AP:LIST?`, `*RST`, `SYSTem:STATus?`). `supported_commands` and the
   parameter schema are already published by the driver.
3. **Backend** — Django already routes the device-command path in
   `web/api/plugins_urls.py`:
   - `GET  /api/list_device_commands/<device_name>/`
   - `POST /api/execute_device_command/<driver_name>/`
4. **Fuzzer** — first-class SCPI fuzzing already exists
   (`iotsploit-fuzzer/.../harnesses/scpi_tcp_harness.py`, `usbtmc_harness.py`)
   driven by the `iot_fuzzer` campaign endpoints. Out of scope here but worth
   noting: the agent can already *start a SCPI fuzzing campaign* if the fuzzer
   endpoints are wrapped; it just can't *send a single SCPI command*.
5. **MCP** — `tools/read_only.py` exposes device reads (`scan_devices`,
   `list_devices`, `device_info`, `get_driver_states`); `tools/write.py`
   exposes `execute_plugin` and target writes. Neither device-command endpoint
   is wrapped. That is the whole gap.

## 2. Phase 1 — wrap the device-command endpoints (recommended)

Two thin tools, each a one-call wrapper over an endpoint that already runs
SCPI. This is the Option-A path and the minimal complete change.

### 2.1 `list_device_commands` (read-only)

Add to `tools/read_only.py`, registered in `register_read_only_tools`:

```python
@mcp.tool()
def list_device_commands(device_name: str) -> dict[str, Any]:
    """List the commands a device driver exposes, with their parameters.

    `device_name` is a driver name from list_device_drivers (e.g. 'drv_esp32').
    For the ESP32 driver these commands are issued to the device over SCPI.
    """
    return _call(
        "list_device_commands",
        lambda: client().get(
            f"/api/list_device_commands/{quote(device_name, safe='')}/"
        ),
    )
```

`quote` is already imported in `read_only.py`; the payload already carries
`commands` and `command_parameters`, so the agent gets a typed menu rather
than having to guess SCPI strings.

### 2.2 `execute_device_command` (mutating)

Add to `tools/write.py`, registered in `register_write_tools` (keeps the
"what can an agent change?" boundary answerable by import, per the module
docstring):

```python
@mcp.tool()
def execute_device_command(
    driver_name: str,
    command: str,
    args: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run one named command on a device driver.

    `command` must be one the driver publishes via list_device_commands.
    For the ESP32 driver the command is carried out over SCPI. Requires the
    device to be scanned/initialized first. Django enforces the bearer token
    for this mutating request.
    """
    def run() -> dict[str, Any]:
        return client().post(
            f"/api/execute_device_command/{quote(driver_name, safe='')}/",
            json={"command": command, "args": args or {}},
        )
    return _call("execute_device_command", run)
```

(Confirm the POST body shape against `execute_device_command` in
`plugin_views.py` before writing — match whatever keys it reads; the snippet
above assumes `command` + `args`.)

### 2.3 Docs + tests

- Add both tools to the **Current Tool Surface** list in
  `iotsploit-mcp/README.md`, `execute_device_command` under the mutating
  group with a one-line note that it inherits the same bearer-token gate as
  `execute_plugin`.
- Extend the existing adapter tests (`tests/test_read_only_tools.py`,
  `tests/test_write_tools.py`) with a fake-client case per tool asserting the
  URL, method, and body — same pattern already used for the current tools. No
  hardware needed.

### 2.4 Why this is enough for "let AI use SCPI"

The ESP32's SCPI vocabulary *is* its command map. Exposing the command map
exposes the SCPI the driver author chose to make safe, with parameter schemas
and the backend's existing validation and auth. The agent drives SCPI without
ever holding a raw socket.

## 3. Phase 2 — generic raw SCPI (deferred, needs a decision)

Phase 1 only reaches instruments that already have a driver. Driving an
*arbitrary* SCPI instrument (bench PSU, scope, SMU) with no bespoke driver
would need a raw `scpi_query` / `scpi_send` path. This is a real feature but a
bigger security surface, so it is listed, not recommended yet.

What it would require:

1. A new Django endpoint that opens a `ScpiClient` over
   `ScpiTcpTransport`/`ScpiSerialTransport` to a caller-named `host:port` or
   serial port and returns the query result. The driver layer currently *owns*
   device connections; a raw endpoint deliberately bypasses that, so it must
   live behind the backend, never in the MCP adapter (architecture rule).
2. MCP tools wrapping it, in `write.py`.
3. Safety: raw SCPI lets an agent point the rig at any reachable network host
   and send arbitrary instrument commands (including `*RST`, output-enable,
   and voltage/current set on a PSU — physically consequential). This is
   exactly the class the README reserves for "the two-key safety gate" and
   backend auth hardening. Options to weigh before building: an allowlist of
   permitted `host:port`/ports, a query-vs-write split (`?` queries looser
   than sets), and the two-key confirmation gate.

Recommendation: ship Phase 1, and only open Phase 2 once the backend auth
hardening / two-key gate referenced in the MCP README exists, since raw SCPI
is one of its motivating cases.

## 4. Out of scope

- Fuzzer campaign MCP tools (separate surface; the SCPI/USBTMC harnesses
  already exist and would be their own wrap).
- Any change to `scpi_client.py`, the ESP32 driver, or the Django
  device-command handlers — Phase 1 reuses them unchanged.
- `iotsploit-ui` — a separate repo; this proposal touches only rig-side code.

## 5. Risk notes

- `execute_device_command` acts on attached hardware. It is no more privileged
  than the already-exposed `execute_plugin`, and sits behind the same Django
  bearer token, so Phase 1 does not widen the trust boundary — it fills in a
  command path that is otherwise reachable from the UI but not from an agent.
- The MCP endpoint remains unauthenticated by design in this MVP; Phase 1 does
  not change that, so the loopback/firewall guidance in the README still
  governs deployment.
