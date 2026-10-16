# TKX-213: assistant runtime implementation

Implements the reviewed v2 plan. The runtime is independent of the socket
consumer; Django owns persistence and a single ASGI process owns active turns.
The Flutter change must be deployed with this backend change: the assistant
WebSocket protocol has changed. Other WebSocket routes are unaffected.

## Run

Apply migrations with the project's Poetry environment:

```bash
poetry run python -m django migrate --settings=iotsploit_django.settings.dev
poetry run iotsploit --runserver
```

The existing service launcher now starts full MCP on the configured MCP port
(default 9900) and inspection MCP on the next port (default 9901). The inspection
instance always binds to loopback. `IOTSPLOIT_MCP_READONLY_PORT` overrides its
port; it must differ from the API, WebSocket, and full MCP ports.

For separately supervised services, start inspection MCP explicitly:

```bash
IOTSPLOIT_MCP_READONLY=1 poetry run iotsploit-mcp http --host 127.0.0.1 --port 9901
```

`IOTSPLOIT_MCP_READONLY_URL` configures the assistant's inspection endpoint.
`IOTSPLOIT_MCP_URL` is used only by the explicitly confirmed Scan devices action.
API model calls, CLI agents, and the four inspection quick actions use the
inspection endpoint. The assistant refuses a server advertising known write
tools; it never falls back to the full endpoint. Inspection mode omits
`scan_devices` and all tools registered by `register_write_tools`, including
device commands and driver enablement. Full MCP keeps its existing behavior.

Use one ASGI worker. For hosts supervised directly with Uvicorn, enable ASGI
lifespan handling so shutdown cancels the runtime's active turns. Conversations
and sequenced events survive restarts; a live subprocess does not. Loading a
conversation whose turn was interrupted by a restart marks that turn failed
and never replays its actions. Forced process/host termination cannot promise
graceful child cleanup.

## What is delivered

- API/local mode, engine or API configuration selection, New chat, history,
  host label, expandable tool results, errors, automatic reconnect, and Stop.
- UUID conversations and a private, persisted client capability identify a
  client's conversations. This is isolation between clients of the existing
  trusted-rig deployment, not a replacement for user authentication. The
  existing backend and full MCP do not authenticate callers; keep the service
  suite on trusted interfaces or behind authenticated access controls.
- One active turn per conversation. Client-provided turn UUIDs are idempotency
  keys. Replay merges by sequence and reconnect never resubmits a prompt.
- OpenAI-compatible (including custom/Ollama), Azure, and Anthropic streaming
  loops with provider-native history, tool-result continuation, an eight-round
  cap and five-minute deadline. Google configurations receive an explicit
  unsupported-tools message. Direct quick-action results become context for
  follow-up questions. No API key is needed for quick actions.
- Cached discovery of every PATH candidate, versions, minimum-version errors,
  manual paths, and refresh. Highest supported version appears first within
  each engine; explicitly selected paths are preserved in conversations.
- Claude Code stream-json, Codex app-server, and OpenCode run-json adapters.
  Stop terminates the owned process group; Codex also attempts turn/interrupt.
  Native session IDs are stored for resume. Sign-in failures give CLI sign-in
  guidance; there is no silent fallback to API billing.

## Socket protocol

Connect to `/ws/ai-assistant/<client-key>/` with a random UUID in hex form;
persist this private client key per backend. The old fixed `ai_assistant_1`
route value is no longer accepted. Initial messages are `discovery` (host,
local availability, binary candidates, active API configurations without keys)
and `sessions` (this client's conversations).

Commands:

| Type | Additional fields |
| --- | --- |
| `session.create` | `mode`: `api` or `local`; optional `config_id` for API, `engine` and detected `binary_path` for local |
| `session.list` | none |
| `session.load` | `session_id`, optional integer `after` sequence |
| `turn.send` | `session_id`, unique UUID `turn_id`, `text` (1–32000 characters) |
| `turn.cancel` | `session_id` |
| `quick_action.run` | `session_id`, unique UUID `turn_id`, `action`; scanning also requires `confirmed: true` |
| `discovery.refresh` | optional `manual: {engine, path}` |

`session.loaded` carries `session`, stored `events`, and current `running`
state. Persisted event types are `user.message`, `turn.started`, `text.delta`,
`tool.start`, `tool.result`, `tool.error`, `turn.done`, `turn.error`, and
`turn.cancelled`. Each includes `session_id`, `turn_id`, monotonic `seq`, and
`created_at`. Tool events include `call_id`; arguments arrive at start and
output at completion. Merge duplicate sequences during replay. A command
validation failure is an unsequenced `error` with a readable `message` and
current `running` state. Client keys isolate conversation access; they do not
authorize arbitrary remote operators to use an otherwise exposed rig.

## CLI isolation and compatibility

Minimum supported versions: Claude Code 2.1.248, Codex 0.160.0, OpenCode 1.17.18.
CLI behavior is version dependent; unsupported binaries remain visible but
cannot be selected. Discovery does not make inference requests.

Each conversation uses a private working directory under
`~/.local/state/iotsploit/assistant` (override with
`IOTSPLOIT_ASSISTANT_STATE_DIR`). Claude uses restricted/bare mode, no built-in
tools, and exclusive MCP configuration. Codex uses a private CODEX_HOME,
read-only sandbox, no approval grants, disabled shell/unified execution,
plugins/apps/browser/code-mode/multi-agent features, and inspection MCP.
OpenCode uses private configuration/data directories, deny-by-default tool
permissions with only `iotsploit_*` allowed, and inspection MCP. Only the
existing credential file is copied into Codex/OpenCode's private state; user
configuration is never edited. Private copies may need a new conversation
after the user signs in again. Do not commit or share the state directory.

The runtime is intended for the existing trusted operator deployment. Tool
configuration and Codex's read-only sandbox do not sandbox the CLI binary
itself or an administrator's managed policies. Third-party/untrusted binaries
must not be installed through the manual-path control.

Official integration references:

- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)
- [OpenCode permissions](https://opencode.ai/docs/permissions/)

## Explicit v1 limits

Docker provides API/quick-action mode; local-agent mode is unavailable. To use
local agents, run Django natively on the host containing the CLIs and their
sign-ins. A laptop-local runtime connected to a remote Pi, model-driven write
tools/approvals, attachments, and a structured client-local Rust scanner bridge
remain later work. The obsolete fenced-text scanner execution path is removed;
the standalone Toolkit scanner is unaffected.

## Validation

Focused tests cover stored event order/client isolation, native adapter config,
shadowed binary selection, Codex resume/permission denial, API tool-result
continuation for both provider formats, runtime cancellation/idempotency,
inspection dispatch refusal, and service-launcher endpoint wiring. Flutter
tests cover replay deduplication, conversation isolation, quick actions without
an API configuration, scan confirmation, and phone layouts in both themes.
The installed Codex 0.160 initialize/thread-start handshake was checked without
requesting inference. Paid model access and real hardware operations require
operator-configured services and are not exercised by the deterministic gates.
