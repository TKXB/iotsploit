# iotsploit-mcp

`iotsploit-mcp` exposes IoTSploit to external coding agents through MCP over
streamable HTTP. It is intended to run on the IoTSploit rig, next to
`iotsploit-django`, `iotsploit-core`, the plugin packages, and the attached
hardware.

## Commands

Start the MCP HTTP endpoint (the default; serves both the Django AI assistant
and external agents):

```bash
export IOTSPLOIT_DJANGO_API_BASE_URL="http://127.0.0.1:8888"
iotsploit-mcp
iotsploit-mcp http --host 127.0.0.1 --port 9900
```

The MCP endpoint is `http://<rig-host>:9900/mcp`.

Bind to `127.0.0.1` for local use (the default). The HTTP endpoint does not
require authentication in this MVP. If you expose the service beyond loopback
(`0.0.0.0` or a LAN address), protect it with a firewall, TLS/reverse proxy, or
re-add authentication before sharing the rig.

## Agent Config

Claude Code:

```bash
claude mcp add --transport http iotsploit http://<rig-host>:9900/mcp
```

Codex, Cursor, or generic MCP config:

```json
{
  "mcpServers": {
    "iotsploit": {
      "type": "http",
      "url": "http://<rig-host>:9900/mcp"
    }
  }
}
```

## Environment

- `IOTSPLOIT_MCP_HOST`: optional default host for the MCP server.
- `IOTSPLOIT_MCP_PORT`: optional default port for the MCP server.
- `IOTSPLOIT_DJANGO_API_BASE_URL`: Django API base URL, default
  `http://127.0.0.1:8888`.
- `IOTSPLOIT_DJANGO_API_TOKEN`: optional bearer token forwarded from MCP to
  Django.
- `IOTSPLOIT_DJANGO_API_TIMEOUT_S`: Django request timeout in seconds.
- `IOTSPLOIT_MCP_LOG_TO_FILE`: set to `1` to enable MCP file logging.

## Current Tool Surface

This branch exposes an HTTP-backed MCP surface. Read-only tools are:

- System: `system_status`, `system_health`, `list_urls`
- Plugins/groups: `list_plugins`, `describe_plugin`, `list_groups`
- Drivers/devices: `list_device_drivers`, `describe_driver`, `scan_devices`,
  `list_devices`, `device_info`, `get_driver_states`
- Targets: `list_targets`, `get_target`, `get_current_target`
- Observations: `get_current_observations`
- Firmware: `firmware_list`, `firmware_info`
- Fuzzer results: `fuzzer_campaign_status`, `fuzzer_campaign_statistics`,
  `fuzzer_results_summary`, `fuzzer_artifacts`
- Tools/files: `get_tools_status`, `get_tool_details`, `list_files`
- Local rig helper: `list_serial_ports`

The mutating tools are `create_target`, `edit_target`, `select_target`,
`execute_plugin` and `record_observations`. `execute_plugin` runs an enabled
exploit plugin against the current target and can interact with attached
hardware or the target. It is temporarily exposed before backend auth
hardening and the two-key safety gate are complete; keep the unauthenticated
MCP endpoint bound to loopback or otherwise protected.

All other mutating or destructive tools remain prohibited until backend auth
hardening and the two-key safety gate described in the implementation proposal
are complete.

`record_observations` records findings an agent produced itself, rather than by
running a plugin. It cannot claim to be a plugin: the backend stores the source
as `agent:<label>`, refusing a caller-supplied `source` outright, and `source`
is one of a scan's comparable scope fields -- so an agent's complete snapshot
replaces only its own previous snapshot of the same scope and can never make a
tool's measurement disappear. Pass `is_complete=False` for a spot check; the
facts are kept as history but do not define current state.
