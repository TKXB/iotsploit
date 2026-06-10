# IoTSploit Agent Setup

IoTSploit's MCP server runs on the rig that has access to the hardware and the
Django backend. External agents connect over HTTP.

1. Start `iotsploit-django` on the rig.
2. Start the MCP server:

```bash
export IOTSPLOIT_MCP_TOKEN="<random token>"
iotsploit-mcp http --host 127.0.0.1 --port 9900
```

3. Configure your agent from `.mcp.json`, replacing the host and token as
needed.

This MVP exposes read-only tools only. Do not add mutating tools until Django
auth and the MCP safety gate are implemented.
