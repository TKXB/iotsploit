# Device Commands over MCP Proposal

## Status

- **State:** Proposal, not started. Revised 2026-10-13 after review: the first
  draft relied on a Django bearer-token gate that does not exist (section 1.6),
  omitted the required `device_id`, and called a generic hardware-command tool
  "curated SCPI". Phase 1a turned out to be already shipped as
  `describe_driver`.
- **Draft date:** 2026-10-13
- **Basis:** Driver commands, including the ESP32's SCPI commands, already run
  end-to-end on the rig (`ScpiClient` → `drv_esp32._command_impl` →
  `DeviceDriverManager.execute_command` → Django `execute_device_command`).
  `iotsploit-mcp` already exposes command discovery (`describe_driver`) but not
  execution, so an agent can list a driver's commands but cannot run one.
- **Estimated effort:** Phase 1a none (already shipped). Phase 1b ~2 hours
  once its prerequisite lands. Phase 2 is a separate decision, not estimated here.
- **Decision owner:** User
- **Blocked on:** Phase 1b — Django API authentication
  (`docs/exec-plans/active/privileged_execution_plan.md`, A1; see the
  tech-debt tracker entry "Mutating `/api/` requests are unauthenticated").

**Goal.** Let an external AI agent discover and run the device commands the
rig's drivers already publish, through MCP, without adding a parallel command
path and without opening an unauthenticated route to hardware.

**What this does not deliver.** Control of real SCPI lab instruments (bench
PSU, scope, SMU). The only SCPI-speaking driver is the ESP32, which speaks
SCPI to IoTSploit's own Wi-Fi firmware (`WIFi:AP:LIST?`). Instrument control
is Phase 2.

## Governing Standards

- `AGENTS.md` — **Delete > Replace > Add**, **Search and reuse first**,
  **Keep scope minimal.** The driver command maps, `DeviceDriverManager`, and
  both Django endpoints exist. This proposal adds adapter tools only.
- `AGENTS.md` — **Solve at the owner.** Authorization belongs in Django, the
  owner of every `/api/` route. An MCP-side denylist of dangerous commands
  would guard a symptom and leave the same route open to any direct caller, so
  it is rejected (section 3).
- `iotsploit-mcp/README.md` — owns the MCP tool surface. Its mutating tools are
  kept in `tools/write.py` so "what can an agent change?" is answered by an
  import.
- `docs/architecture.md` — ports-and-adapters. MCP is an adapter over the
  Django HTTP API; it never reaches hardware directly.

## 1. What exists today

1. **SCPI client** — `iotsploit-drivers/.../esp32/scpi_client.py` provides
   `ScpiClient` (`send_command`, `query`, `reset`, `get_status`,
   `get_version`) over `ScpiTcpTransport` and `ScpiSerialTransport`. It lives
   under `esp32/` and has no other user.
2. **Driver command maps** — every driver publishes `supported_commands` and,
   where a command takes input, a parameter schema. The ESP32's map
   (`drv_esp32.py:21`) is `scan_wifi`, `get_version`, `get_status`, `reset`,
   `start_wifi_monitor`, `stop_wifi_monitor`, `flash_firmware`, `erase_flash`,
   `get_chip_info`. J-Link, ST-Link, GreatFET, SocketCAN/PCAN, FT2232, the
   logic analyser, and the FPGA publish their own; none of those use SCPI.
3. **Manager** — `DeviceDriverManager.execute_command(driver_name, command,
   device_id, args)` (`iotsploit-core/.../device_manager.py:294`) refuses a
   disabled driver, then `_handle_command` looks the device up with
   `driver.get_device(device_id)` and fails with "Device … not found" when it
   is absent (`:671`). A device only needs to have been scanned; the UI never
   connects first (`:676`).
4. **Backend routes** — `web/api/plugins_urls.py`:
   - `GET  /api/list_device_commands/<device_name>/` returns `commands` and
     `command_parameters`.
   - `POST /api/execute_device_command/<driver_name>/` reads `command`
     (required), `device_id`, and `args` (`plugin_views.py:772`).
5. **MCP** — `tools/read_only.py` exposes `list_device_drivers`,
   `describe_driver`, `scan_devices`, `list_devices`, `device_info`,
   `get_driver_states`. `describe_driver` already wraps
   `GET /api/list_device_commands/<device_name>/` (`read_only.py:114`), so
   discovery is done. Only `execute_device_command` is unwrapped.
6. **Authorization: none.** Both device-command views, like `execute_plugin`,
   are `@csrf_exempt` with no authentication. No middleware enforces a token on
   `dev` or `main`, and `dev`'s `DjangoHttpClient` sends none. The MCP README's
   statement that "Django requires the configured bearer token" for mutating
   requests describes the privileged-execution plan's A1, which is recorded as
   complete on `security/privileged-execution-boundary` but never reached
   `dev` or `main`. Anything that can reach Django on the rig, or the MCP
   endpoint, can already run `execute_plugin` today.

## 2. Phase 1a — command discovery (already shipped)

The first draft proposed a new `list_device_commands` MCP tool. It already
exists as `describe_driver(device_name)`, which returns the endpoint's
`commands` and `command_parameters` and is listed in the README and in
`docs/writing-plugins.md`. A second tool for the same route would duplicate it,
so nothing is added. An agent discovers commands today with
`list_device_drivers` → `describe_driver`.

## 3. Phase 1b — `execute_device_command` (mutating, after auth lands)

### 3.1 Why it waits

This tool can flash or erase an ESP32, reset any device, drive a debugger
(J-Link, ST-Link), and transmit on a CAN bus. Today the route behind it is
unauthenticated, so adding an MCP tool for it would give unauthenticated
access to physically consequential, partly irreversible hardware actions
through one more door.

`execute_plugin` already has the same hole, which is an argument for closing
the hole, not for copying it. Three options were weighed:

| Option | Verdict |
| --- | --- |
| Ship now; rely on loopback binding | Rejected. Loopback is the only control, and the README already tells operators how to bind beyond it. |
| Ship now with an MCP-side denylist (`flash_firmware`, `erase_flash`, …) | Rejected. Guards a symptom in the wrong owner; Django's route stays open to direct callers; the list rots as drivers add commands. |
| Wait for Django API auth (privileged-execution plan A1) | **Selected.** Fixes the owner, covers `execute_plugin` too, and the MCP tool becomes a plain wrapper. |

### 3.2 The tool, once A1 is merged

Add to `tools/write.py`, in `register_write_tools`:

```python
@mcp.tool()
def execute_device_command(
    driver_name: str,
    device_id: str,
    command: str,
    args: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run one command a device driver publishes, on one device.

    Get `command` and its `args` schema from describe_driver, and
    `device_id` from scan_devices or list_devices. The device must have been
    scanned; it need not be connected. Commands act on real hardware and some
    are irreversible (flash_firmware, erase_flash), so state what a command
    will do before running it.
    """
    def run() -> dict[str, Any]:
        return client().post(
            f"/api/execute_device_command/{quote(driver_name, safe='')}/",
            json={"command": command, "device_id": device_id, "args": args or {}},
        )
    return _call("execute_device_command", run)
```

`write.py` must import `quote`. Add the tool to the README's mutating list and
add one fake-client case to `tests/test_write_tools.py` asserting the URL and
body.

## 4. Phase 2 — raw SCPI to arbitrary instruments (deferred)

This is the only phase that delivers AI control of lab instruments. It needs:

1. `ScpiClient` and its transports moved out of `esp32/` to a shared owner
   (e.g. `iotsploit_drivers/scpi/`), with the ESP32 driver importing from
   there.
2. A backend owner for instrument connections. Prefer an `scpi_instrument`
   device driver configured with instrument addresses, publishing `query` and
   `write` commands, over a free-form raw endpoint: it reuses the driver
   lifecycle, device locking, and Phase 1b's tool unchanged, and adds no new
   route.
3. Safety beyond A1: instrument addresses come from rig configuration, never
   from the caller (otherwise the rig becomes a TCP client to any host the
   agent names), and the plan must decide whether `write` (output enable,
   voltage/current set) requires the two-key confirmation gate the MCP README
   reserves for mutating hardware access.

Write it as its own plan when someone needs it.

## 5. Out of scope

- Fuzzer campaign MCP tools. The SCPI-TCP and USBTMC harnesses exist and are
  their own wrap.
- Changes to `scpi_client.py`, any driver, `DeviceDriverManager`, or the
  Django device-command views. Phase 1b reuses them unchanged.
- `iotsploit-ui`, a separate repository.

## 6. Risk notes

- Phase 1b adds an agent-facing path to every driver command on the rig. It is
  safe only behind enforced Django auth; do not merge it ahead of A1.
- The MCP endpoint stays unauthenticated by design in this MVP. A1
  authenticates MCP→Django, not agent→MCP, so the loopback guidance in the
  MCP README still governs who can reach the tools at all.
