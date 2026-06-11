# iotsploit-mcp

`iotsploit-mcp` exposes IoTSploit to external coding agents through MCP over
streamable HTTP. It is intended to run on the IoTSploit rig, next to
`iotsploit-django`, `iotsploit-core`, the plugin packages, and the attached
hardware.

## Commands

Start the legacy WebSocket bridge used by the existing UI:

```bash
iotsploit-mcp
iotsploit-mcp ws --host 0.0.0.0 --port 9998
```

Start the MCP HTTP endpoint for external agents:

```bash
export IOTSPLOIT_DJANGO_API_BASE_URL="http://127.0.0.1:8888"
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

This branch exposes a read-only HTTP-backed MVP:

- System: `system_status`, `system_health`, `list_urls`
- Plugins/groups: `list_plugins`, `describe_plugin`, `list_groups`
- Drivers/devices: `list_device_drivers`, `describe_driver`, `scan_devices`,
  `list_devices`, `device_info`, `get_driver_states`
- Targets: `list_targets`, `get_current_target`
- Firmware: `firmware_list`, `firmware_info`
- Fuzzer results: `fuzzer_campaign_status`, `fuzzer_campaign_statistics`,
  `fuzzer_results_summary`, `fuzzer_artifacts`
- Tools/files: `get_tools_status`, `get_tool_details`, `list_files`
- Local rig helper: `list_serial_ports`

Mutating and destructive tools are intentionally not exposed in this MVP.
They require backend auth hardening and the two-key safety gate described in
the implementation proposal.
