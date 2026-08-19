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

The MCP server may expose the read-only tools plus exactly three target-management
mutations -- `create_target`, `edit_target`, `select_target` -- as well as
`record_observations` and `execute_plugin`. `execute_plugin` is a temporary,
explicit exception while Django auth and the MCP safety gate are unfinished;
keep MCP bound to loopback or protect it externally. Do not add any other
mutating or destructive tools until Django auth and the MCP safety gate are
implemented.

`record_observations` is permitted because it cannot forge provenance: the
backend assigns the source as `agent:<label>`, and since `source` is part of a
scan's comparable scope, an agent's snapshot can only replace its own and never
a plugin's measurement. Any future write tool needs a comparable argument for
why it is safe without auth, not just a use case.

## Execution Plans

Plans live in `docs/exec-plans/`: `active/` (in progress), `pending/`
(decided, not started), `completed/` (done/stale — don't act on unless stated).
Search there before writing a new plan.

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
