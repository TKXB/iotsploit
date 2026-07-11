# IoTSploit Agent Setup

Read `.agents/local.md` when it exists for machine-specific toolchain paths and
commands. Use Poetry for Python dependency management and command execution.

IoTSploit's MCP server runs on the rig that has access to the hardware and the
Django backend. External agents connect over HTTP.

1. Start `iotsploit-django` on the rig.
2. Start the MCP server:

```bash
iotsploit-mcp http --host 127.0.0.1 --port 9900
```

3. Configure your agent from `.mcp.json`, replacing the host as needed.

This MVP exposes read-only tools only. Do not add mutating tools until Django
auth and the MCP safety gate are implemented.

## Pre-Commit Test Gate

Before committing Python code, run the full test gate:

```bash
tools/testing/test-python-full.sh
```

See `.agents/standards/testing.md` for the complete policy.
Enable the local git hook once per working copy:

```bash
git config core.hooksPath tools/git-hooks
```
