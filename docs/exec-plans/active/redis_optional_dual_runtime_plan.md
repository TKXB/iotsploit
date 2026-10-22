# Optional Redis Dual-Runtime Execution Plan

## Status

- **State:** Implemented — hardware acceptance pending
- **Decision date:** 2026-09-01
- **Revised:** 2026-09-01 (code review against the current tree; see
  [Revision Notes](#revision-notes))
- **Selected option:** Option B — dual runtime modes
- **Decision owner:** User
- **Estimated effort:** 9–13 engineering days (72–104 hours)

This plan supersedes the implementation estimate in
[`../completed/redis_removal_proposal.md`](../completed/redis_removal_proposal.md).
That document remains useful historical analysis, but its one-day estimate predates the
durable interactive-execution lifecycle, separate Celery queues, and current streaming
work. [`../completed/redis_decoupling_analysis.md`](../completed/redis_decoupling_analysis.md)
is also background only.

## Governing Standards

These bind the implementation and are quoted here because they change specific decisions
below, not as boilerplate.

- `AGENTS.md` — Delete > Replace > Add; solve at the owner; search and reuse before
  adding; tests are out of scope by default. The work below is framed as a deletion
  with a small local runner attached, not as a new runtime layer.
- `docs/architecture.md` — core never imports Django, Celery, Channels, or Redis, and
  **adapters are selected only in composition roots**: `core_container.py` and
  `iotsploit_mcp/composition_root.py`. Phase 1 exists to restore that rule, which the
  `use_celery` parameter currently breaks.
- `.agents/standards/testing.md` — `service`-marked tests (anything needing Redis) are
  **excluded** from `tools/testing/test-python-full.sh` by policy. Distributed-mode
  verification is therefore a separate manual run, not something the gate will catch.
  Report passed/failed/skipped/warning counts. Never `git commit --no-verify`.
- `.agents/local.md` — run everything through Poetry from the repository root.

## Decision

Make the Redis **service** and its Python clients optional without deleting the working
Redis/Celery deployment path.

The application will have exactly two startup-selected modes:

| Mode | Execution | Shared state | WebSocket transport | Process model |
|---|---|---|---|---|
| `local` | In-process background workers | SQLite | Channels in-memory layer | One ASGI process |
| `distributed` | Celery workers | SQLite, with Redis as transport only | Redis channel layer | Multiple processes |

Use one explicit setting, provisionally `IOTSPLOIT_RUNTIME=local|distributed`. Invalid
values fail during startup. The default will be `local` unless release compatibility
evidence collected in Phase 0 shows an existing packaged deployment depends on an
implicit distributed default.

Mode selection happens once at startup. There is no automatic mid-run failover from
distributed to local mode: after a broker outage, resubmitting work locally could execute
the same hardware action twice.

## Goal

With no Redis server running and no Redis/Celery Python packages installed, local mode
must retain the project's currently working single-operator functionality:

- Django HTTP APIs, ORM state, targets, drivers, CLI, and MCP;
- synchronous and asynchronous plugins;
- interactive prompts, answers, timeouts, and cooperative cancellation;
- long-running and streaming plugins with live WebSocket updates;
- fuzzer campaign start, status, statistics, pause, reset, and stop;
- non-interactive privileged plugin execution; and
- recovery of persisted execution state after a client reconnect.

Distributed mode must retain Celery queues, Redis-backed cross-process WebSockets,
worker isolation, retries, and existing multi-process deployment capability.

## Non-goals

- Hot failover between runtime modes.
- Resuming a running local thread after the ASGI process restarts.
- Safely force-killing an arbitrary Python thread. Local cancellation is cooperative;
  distributed mode retains process termination.
- Adding multi-worker support to local mode.
- Replacing Redis with another mandatory broker.
- Adding privileged interactive-plugin support. That is already a later phase of
  [`../active/interactive_exploit_plugin_plan.md`](../active/interactive_exploit_plugin_plan.md).
- Unrelated cleanup in the legacy task, fuzzer, or deployment code.
- Fixing the Docker interactive/streaming queue gap recorded in Fact 15 beyond what
  Phase 7's distributed profile needs to be honest.

## Current Facts

Line references are from the tree at revision time and are meant to be re-checked, not
trusted blindly.

### Existing seams to reuse

- Core already defines `TaskRunner`; Celery and memory adapters already sit outside core.
- Core already defines `StreamBackend`; Django supplies the concrete streaming adapter.
- `PluginExecution` and `InputRequest` already persist execution status, results, errors,
  prompts, answers, and cancellation in SQLite.
- The durable interaction adapter already polls SQLite deliberately, so interactive
  request/answer delivery does not require Redis.
- `FuzzingCampaign` already owns persisted campaign identity and lifecycle **fields**,
  but not campaign identity in practice — see Fact 13.

### Remaining hard coupling

1. `InProcessTaskRunner.submit()` is a stub and does not execute a plugin. There are two
   copies of the same stub: `adapters/memory/task_runner.py` and
   `iotsploit-mcp/.../adapters/task_runner_local.py`.
2. Plugin views and CLI code still call Celery or `AsyncResult` directly.
3. Interactive and streaming views submit `run_execution_task` directly to Celery.
4. Base settings hardcode Redis as Celery broker, result backend, and channel layer
   (`settings/base.py:99-107,149-157`).
5. `IoTFuzzerManager` treats Redis as the campaign-state source of truth.
6. `DjangoStreamManager` uses Redis sets for active and broadcasting channels.
7. The privileged subprocess sends its result back through a Redis key.
8. The CLI refuses to start services when Redis is unavailable.
9. Local startup currently creates separate HTTP and WebSocket processes; an in-memory
   channel layer cannot cross that boundary.
10. `celery`, `redis`, and `channels-redis` are mandatory package dependencies and are
    imported from local startup paths, including `tasks/__init__.py`, which imports
    `celery_app` unconditionally.

### Defects confirmed during review

These are pre-existing and are named because a phase below either depends on them or
must delete them. None is licence for unrelated cleanup.

11. **`use_celery` is already inert.** `wiring.py:29` memoizes `_exploit_mgr`, so
    `use_celery` is honoured only on the first call in a process and silently ignored
    afterwards. Whichever caller runs first picks the runner for everything. Phase 1 is
    therefore a correctness fix, not tidying.
12. **The in-memory channel layer is not thread-safe.** `channels` 4.1.0's
    `InMemoryChannelLayer` is a plain `dict` of `asyncio.Queue`. Every producer in local
    mode will be a worker thread calling `async_to_sync(group_send)`, which runs `send()`
    on a *fresh* loop in that thread; `put_nowait` then calls `set_result()` on a future
    owned by the Daphne loop with no `call_soon_threadsafe`. `call_soon`'s thread check
    is debug-only, so this does not raise — it defers to the Daphne loop's next wakeup
    and races the shared dicts. Roughly ten emit sites are affected: `tools/xlogger.py:23`,
    `tools/iot_fuzzer_bridge.py:212,222`, `adapters/django/interaction/events.py:40`,
    `tasks/plugin_tasks.py:106`, and six in `tasks/legacy_tasks_impl.py`.
13. **Fuzzer campaigns have no durable identity.** `iot_fuzzer/views_campaign.py:66`
    does `FuzzingCampaign.objects.get_or_create(name=name)` where `name` defaults to
    `"{PROTOCOL} Campaign"`, then overwrites `campaign_uuid` on that row. Every CAN run
    recycles one row. Redis hides this by keying per UUID.
14. **The fuzzer builds its adapters twice.** `iot_fuzzer_manager.py:275-276` creates an
    orchestrator and monitor pair, and `legacy_tasks_impl.py:91-94` creates a *second*
    pair with a different `create_monitor_adapter` signature and overwrites the manager's
    dict. Two processes hide it today; one process would not.
15. **Docker never starts the interactive or streaming queues.**
    `docker/supervisord.conf` runs exactly one Celery worker on default queues, so
    interactive plugins queued in the Docker deployment currently wait forever.
16. `IoTFuzzerManager.__init__` **raises** on `redis.ConnectionError`
    (`iot_fuzzer_manager.py:61`), so the manager cannot be constructed at all without a
    reachable Redis.
17. `_start_campaign_task` catches a Celery dispatch failure, sets
    `task_id = f"mock_{campaign_id}"` (`iot_fuzzer_manager.py:594-596`), and reports the
    campaign as started while nothing runs.
18. `sweep_stranded_executions` (`tasks/interaction_tasks.py:101`) has no scheduler
    anywhere in the repository — no beat schedule, no CLI invocation.
19. `plugin_sudo_runner.py` calls `logging.basicConfig` twice (`:38` and `:95`); the
    second is a no-op because the first already installed a stderr handler.

## Architecture

```text
HTTP / CLI submission
        |
        v
PluginExecution row in SQLite
        |
        v
Runtime-selected TaskRunner
  local thread queue       Celery queue
          \                 /
           v               v
       one shared execution function
                   |
          SQLite status and result
                   |
         runtime-selected event sink
   local: marshal onto the ASGI loop   distributed: Redis channel layer
                   |
            Channels group_send
```

### Source-of-truth rule

SQLite owns durable execution and campaign state in **both** modes. Redis is transport,
never authoritative business state. This prevents two implementations of status, result,
and cancellation semantics.

### Thread-to-loop rule

In local mode, no worker thread calls `async_to_sync(channel_layer.group_send)` directly.
The ASGI process captures its running loop at startup, and every local-mode emit is
marshalled with `asyncio.run_coroutine_threadsafe`. This is one wrapper at the existing
emit boundary, not a new messaging abstraction — see Fact 12 for why the naive path
fails silently rather than loudly.

No new generic cache, task-state registry, or repository abstraction will be introduced.
The change extends the existing owners:

- execution state stays in the interaction execution models/service;
- task dispatch stays behind `TaskRunner`;
- fuzzer state stays with `FuzzingCampaign`/`IoTFuzzerManager`; and
- stream tracking stays in the existing stream adapter.

## Deletion Inventory

`AGENTS.md` puts deletion first, so the work is tracked as a net removal. Each item is
deleted in the phase named, not retained as a fallback.

| Delete | Where | Phase |
|---|---|---|
| `use_celery` parameter and every caller, including `SAT_SHELL_USE_CELERY` | `wiring.py`, `core_container.py`, `exploit_manager_factory.py`, `console.py:204`, 4 task/view call sites | 1 |
| Duplicate `InProcessTaskRunner` stub | `iotsploit-mcp/.../task_runner_local.py` | 1 |
| `ports_impl/task_runner.py` re-export | Django package | 1 |
| Direct `AsyncResult` status/result path | `plugin_views.py:24,842`, `consumers_impl.py:88`, `plugin_commands.py:166-170` | 2 |
| Duplicate execution body | `legacy_tasks_impl.py:14-63` (superseded by `plugin_tasks`) | 2 |
| `sweep_stranded_executions` or its unscheduled state | `interaction_tasks.py:101` | 2 |
| Redis active/broadcast sets | `stream_manager.py:33-79` | 4 |
| `_store/_get/_update/_remove_campaign_state`, `_calculate_final_statistics_from_redis` | `iot_fuzzer_manager.py` | 5 |
| Duplicate adapter construction | `iot_fuzzer_manager.py:275-276` or `legacy_tasks_impl.py:91-94` | 5 |
| `mock_<campaign_id>` silent-success fallback | `iot_fuzzer_manager.py:594-596` | 5 |
| Redis task-ID/TTL/cleanup IPC on both sides | `privilege_mgr.py`, `plugin_sudo_runner.py` | 6 |
| Redundant second `basicConfig` | `plugin_sudo_runner.py:95` | 6 |
| Embedded Redis server in the default image | `docker/supervisord.conf:19-28` | 7 |
| Unconditional `celery_app` import | `tasks/__init__.py:9` | 7 |

## Implementation Phases

Each phase keeps distributed mode working. Local mode is not declared complete until all
acceptance criteria pass.

### Phase 0 — Baseline and contract inventory

1. Read `.agents/standards/testing.md` before changing tests.
2. Run the full Python gate and record pre-existing failures separately, with counts.
3. Capture the HTTP and WebSocket payloads used for:
   - normal asynchronous plugin completion, including the `/ws/exploit/<task_id>/`
     `{status: pending|complete, result}` envelope, which differs from
     `PluginExecutionConsumer`'s;
   - interactive execution and cancellation;
   - streaming CAN execution; and
   - fuzzer campaign lifecycle.
4. Confirm which public launch paths depend on ports 8888 and 9999. Known consumers:
   `tools/discovery_server.py:28,136`, `docker/nginx.conf:32,46,55`, `docker-compose.yml`,
   `iotsploit-cli/.../can_live.py:22-23`, `ui/lib/providers/config_provider.dart:13`, and
   a hardcoded `ws://10.8.0.3:9999` in `ui/lib/screens/tasks/components/esp32.dart:24`.
5. Confirm Facts 11-19 still hold. Facts 13, 14, and 15 are the ones that change a
   phase's shape if they have since been fixed.

Exit condition: current behavior and external contracts are recorded before triggers are
moved.

### Phase 1 — Runtime selection at composition roots

1. Add and validate the two-valued runtime setting.
2. Make settings choose:
   - local: in-memory channel layer and no Celery broker/result configuration;
   - distributed: existing Redis broker, result backend, and Redis channel layer.
3. Select the task runner and stream backend **only** in the two composition roots named
   in `docs/architecture.md`. Delete the `use_celery` parameter outright rather than
   defaulting it — per Fact 11 it does not currently do what its call sites assume.
4. Collapse the two identical `InProcessTaskRunner` stubs into the one the composition
   roots share, and delete the `ports_impl/task_runner.py` re-export, which drags Celery
   into any importer.
5. Keep core free of Django, Celery, Channels, and Redis imports.
6. Add a concise startup log stating the selected mode and its limitations.

Exit condition: importing and initializing Django in local mode makes no Redis connection
and imports no Redis/Celery-only adapter, and no caller can request a runner that the
composition root did not choose.

### Phase 2 — One durable plugin-execution lifecycle

1. Extract the execution body currently owned by the Celery task into one ordinary
   Django adapter function that:
   - marks the `PluginExecution` running;
   - rebuilds the target snapshot;
   - binds the durable interaction adapter;
   - configures the stream backend;
   - executes through `run_plugin_in_process()`;
   - records observations through the existing manager path; and
   - marks completion, failure, timeout, or cancellation exactly once.
2. Keep the Celery task as a thin distributed adapter around that function.
3. Replace the memory runner stub with a real local runner that invokes the same function
   on background threads.
4. Preserve the current queue isolation with bounded concurrency:
   - standard work: small configurable pool;
   - interactive work: concurrency 1; and
   - streaming work: concurrency 1.

   `_execution_queue` (`plugin_views.py:27`) already picks the queue name; local mode maps
   the same three names to thread pools rather than introducing a second routing rule.
5. Create the durable execution row before either adapter dispatches work.
6. Return the durable execution identifier as the transport-neutral task handle. Existing
   `task_id` response fields may continue to carry that opaque identifier so public HTTP
   payloads do not need a compatibility branch.
7. Decide and record what happens to `/ws/exploit/<task_id>/`. Its consumer polls
   `celery_app.AsyncResult` once a second and emits an envelope the durable execution
   socket does not use, so "no compatibility branch" is true of the HTTP payload but not
   of this socket. Either back the existing envelope with durable state, or retire the
   consumer and move the Flutter client — do not leave both shapes live.
8. Route direct `.delay()`, `apply_async()`, `AsyncResult`, status, and revoke call sites
   through the durable lifecycle. Delete the superseded direct Celery result path,
   including the duplicated execution body in `legacy_tasks_impl.py:14-63`.
9. Make CLI result waiting query the durable execution state instead of Celery.
10. On local-process startup, mark orphaned queued/running local executions as
    interrupted; do not pretend to resume work that no longer exists.
11. Resolve `sweep_stranded_executions` (Fact 18): give it a caller in whichever mode
    still needs it, or delete it. It is currently dead code that looks like a safety net.

Cancellation rule:

- both modes immediately record cancellation in SQLite;
- interactive waits and plugins using cancellation checkpoints unwind cooperatively;
- distributed mode may additionally revoke/terminate the Celery task; and
- local mode never reports that a still-running thread was forcibly stopped.

Exit condition: synchronous, asynchronous, interactive, and streaming plugins use one
status/result owner, and no local caller needs `AsyncResult`.

### Phase 3 — Single-process local ASGI and WebSockets

1. In local mode, launch one Daphne process that serves both HTTP and WebSockets.
2. Keep both existing ports on that one process rather than changing the topology.
   Daphne's `--endpoint` is `append`-capable, and a single process binding both ports was
   verified against the pinned Daphne during review:

   ```bash
   poetry run daphne \
     -e tcp:8888:interface=0.0.0.0 \
     -e tcp:9999:interface=0.0.0.0 \
     iotsploit_django.asgi:application
   ```

   This keeps `tools/discovery_server.py`, `docker/nginx.conf`, `can_live.py`, the Flutter
   `config_provider`, and the hardcoded `esp32.dart` socket untouched, and removes the
   port-migration risk entirely. Only fall back to a single shared port if Phase 0 finds a
   consumer this cannot satisfy.
3. Do not start Django's separate development server or any Celery worker in local mode.
4. In distributed mode, retain the existing multi-process topology.
5. Update the local Docker/Supervisor configuration to run the one ASGI process. Nginx
   needs no change if step 2 holds.
6. Implement the thread-to-loop rule: capture the ASGI loop at startup and marshal every
   local-mode `group_send` through it. Apply it at the existing emit sites listed in
   Fact 12 rather than at each caller.
7. Verify execution events, logs, prompts, and device stream frames actually arrive —
   under sustained load, not a single event. Fact 12's failure mode is delay and loss,
   not an exception, so a smoke test that sends one message will pass on broken code.

Exit condition: live WebSocket behavior works with Redis stopped because every local
producer and consumer shares one process, and events emitted from worker threads arrive
promptly and in order under load.

### Phase 4 — Redis-free stream tracking

1. Retain `DjangoStreamManager` as the owner; do not create a parallel stream manager.
2. In local mode, replace Redis active/broadcast sets with process-local sets protected
   for concurrent access.
3. In distributed mode, retain shared Redis tracking where cross-process introspection is
   required.
4. Move the Redis import inside the distributed path so the module imports without the
   optional package installed.
5. Preserve the `StreamBackend` protocol and `active_channels` HTTP response.

Exit condition: device registration, bidirectional stream data, active-channel listing,
and broadcast cleanup work in both modes.

### Phase 5 — Make fuzzer state database-owned

Ordered so identity is fixed before state moves onto it. Doing 5.1 second would migrate
Redis's per-UUID state onto a row that is recycled by name.

1. **Fix campaign identity first (Fact 13).** Key the `FuzzingCampaign` row on
   `campaign_uuid` — `get_or_create(campaign_uuid=...)` — so each run owns a row. Until
   this holds, run N+1 overwrites run N's state.
2. **Resolve the duplicate adapter construction (Fact 14)** before relocating the loop.
   Decide which of `iot_fuzzer_manager.py:275-276` and `legacy_tasks_impl.py:91-94` is the
   real construction — note only the latter passes the orchestrator to
   `create_monitor_adapter` — and delete the other. In one process the duplicate would
   open the same CAN or serial hardware twice.
3. Add the minimum migration needed to extend `FuzzingCampaign` with a JSON runtime-state
   field for AFL-style counters and other currently Redis-only state. Reuse the existing
   `status`, `started_at`, `completed_at`, and statistics fields rather than duplicating
   them inside JSON.
4. Replace `_store_campaign_state`, `_get_campaign_state`, `_update_campaign_state`,
   `_remove_campaign_state`, and active-campaign lookup with atomic ORM operations.
5. Make `IoTFuzzerManager.__init__` constructible without Redis (Fact 16); today it
   raises, so nothing downstream of it can be tested in local mode.
6. Relocate the campaign loop from the Celery task into `IoTFuzzerManager`, its existing
   owner. Keep the Celery task as a thin distributed wrapper.
7. Dispatch the same loop to a local background worker in local mode. Delete the
   `mock_<campaign_id>` fallback (Fact 17) rather than porting it — reporting a campaign
   as started when nothing runs is the symptom-guard `AGENTS.md` forbids.
8. Keep pause/stop control database-driven so the process running the campaign observes
   state changes in either mode.
9. Keep WebSocket notifications non-authoritative; clients recover through HTTP/database
   state after missed messages.
10. Delete Redis-specific method names, comments, and error messages once no caller relies
    on them.

Exit condition: the complete fuzzer lifecycle and statistics endpoints work with Redis
unavailable; two consecutive campaigns keep separate state; hardware adapters are
constructed exactly once per campaign; and distributed workers read the same database
state.

### Phase 6 — Remove Redis from privileged result IPC

1. Have `PrivilegeManager` pass a result-file path to the subprocess and have the runner
   write its single JSON document there.

   Prefer this over reserving stdout. Root plugins shell out to tools that write to file
   descriptor 1 directly, and `contextlib.redirect_stdout` only rebinds Python's
   `sys.stdout`, so a stdout contract would be silently broken by the first plugin that
   calls an external binary. A file also survives the subprocess writing progress output.
   If stdout is chosen anyway, the redirect must be at the file-descriptor level
   (`os.dup2` fd 1 to fd 2 for the plugin's duration), and that must be stated explicitly.
2. Keep plugin logging on stderr. This already works — `plugin_sudo_runner.py:38` installs
   a stderr handler at import — so delete the redundant second `basicConfig` at `:95`
   rather than adding a third path.
3. Parse the result file after a successful subprocess exit; treat a missing or unparseable
   file as a failure with the subprocess's stderr attached.
4. Remove task IDs, Redis keys, TTL handling, connection checks, and result cleanup from
   both sides.
5. Preserve subprocess isolation and existing result serialization.
6. Do not expand this phase into privileged interactive execution.

Exit condition: a non-interactive root-required plugin returns its structured result with
no Redis import or connection, and a plugin that prints to stdout or shells out to a
noisy tool does not corrupt that result.

### Phase 7 — Optional dependencies and deployment

1. Move `celery`, `redis`, and `channels-redis` to an optional `distributed` extra in
   `iotsploit-django`.
2. Remove unconditional imports from package initializers, views, consumers, CLI startup,
   and local composition paths. `tasks/__init__.py:9` imports `celery_app` — and therefore
   `celery` — for every importer of the package.
3. Keep the repository development environment able to run distributed tests explicitly.
4. Make CLI startup mode-aware:
   - local: no Redis preflight and no Celery processes;
   - distributed: Redis preflight and all required workers.
5. Make the default Docker profile local and remove the embedded Redis server from that
   image.
6. Provide an explicit distributed Docker profile/service composition rather than hiding
   Redis inside the application container. That profile must start the `interactive` and
   `streaming` workers; per Fact 15 the current one does not, so the distributed
   acceptance suite will fail on Docker until it does.
7. Update README and Django package documentation with commands, topology, limitations,
   and migration guidance.

Exit condition: a clean local installation does not install Redis/Celery clients, and the
distributed extra restores the full broker-backed deployment including all three queues.

### Phase 8 — Validation and cleanup

1. Work through the Deletion Inventory and confirm each row is gone, not disabled.
2. Search the repository for remaining unconditional Redis/Celery imports and direct task
   submissions.
3. Run focused local-mode tests with port 6379 closed/unreachable.
4. Run distributed-mode tests explicitly: `poetry run pytest -m service` with Redis
   available. Per `.agents/standards/testing.md` these are **excluded** from the gate, so
   the gate passing is not evidence that distributed mode still works.
5. Run `tools/testing/test-python-full.sh` and report passed/failed/skipped/warning counts.
6. Validate on the hardware rig in both modes where the feature depends on real CAN,
   serial, USB, or privileged access. Fuzzer adapter construction (Phase 5.2) and
   privileged IPC (Phase 6) are the two paths a non-hardware test cannot cover.
7. Update HTTP/WebSocket contract snapshots only if an intentional contract change was
   approved during implementation — the `/ws/exploit/` decision from Phase 2.7 is the
   expected one.

Exit condition: all acceptance criteria pass, then move this file from `pending/` to
`completed/` in the same change that finishes the work. Move it to `active/` only when
implementation actually begins.

## Expected File Impact

Prefer modifying the existing owner. A new Python file is justified only for the shared
non-Celery execution function, because placing it in a Celery task module would make the
optional dependency import during local startup.

Composition and runtime selection:

- `iotsploit-django/src/iotsploit_django/settings/base.py`
- `iotsploit-django/src/iotsploit_django/composition_root/wiring.py`
- `iotsploit-django/src/iotsploit_django/composition_root/core_container.py`
- `iotsploit-django/src/iotsploit_django/adapters/django/exploit_manager_factory.py`
- `iotsploit-core/src/iotsploit_core/ports/task_runner.py`
- `iotsploit-django/src/iotsploit_django/adapters/memory/task_runner.py`
- `iotsploit-django/src/iotsploit_django/adapters/django/task_runner.py`
- `iotsploit-django/src/iotsploit_django/ports_impl/task_runner.py` (delete)
- `iotsploit-mcp/src/iotsploit_mcp/composition_root.py`
- `iotsploit-mcp/src/iotsploit_mcp/adapters/task_runner_local.py` (delete)
- `iotsploit-cli/src/iotsploit_cli/console.py`

Execution lifecycle:

- `iotsploit-django/src/iotsploit_django/adapters/django/interaction/service.py`
- `iotsploit-django/src/iotsploit_django/adapters/django/interaction/events.py`
- `iotsploit-django/src/iotsploit_django/tasks/__init__.py`
- `iotsploit-django/src/iotsploit_django/tasks/celery_app.py`
- `iotsploit-django/src/iotsploit_django/tasks/interaction_tasks.py`
- `iotsploit-django/src/iotsploit_django/tasks/plugin_tasks.py`
- `iotsploit-django/src/iotsploit_django/tasks/legacy_tasks_impl.py`
- `iotsploit-django/src/iotsploit_django/view_handlers/plugin_views.py`
- `iotsploit-django/src/iotsploit_django/websocket/consumers_impl.py`
- `iotsploit-cli/src/iotsploit_cli/commands/plugin_commands.py`

Channels and streaming:

- `iotsploit-django/src/iotsploit_django/adapters/django/stream_manager.py`
- `iotsploit-django/src/iotsploit_django/tools/xlogger.py`
- `iotsploit-django/src/iotsploit_django/tools/iot_fuzzer_bridge.py`

Fuzzer:

- `iotsploit-django/src/iotsploit_django/tools/iot_fuzzer_manager.py`
- `iotsploit-django/src/iotsploit_django/tasks/fuzzer_tasks.py`
- `iotsploit-django/src/iotsploit_django/iot_fuzzer/views_campaign.py`
- `iotsploit-django/src/iotsploit_django/adapters/django/iot_fuzzer/models.py`

Privileged execution:

- `iotsploit-django/src/iotsploit_django/tools/privilege_mgr.py`
- `iotsploit-django/src/iotsploit_django/tools/plugin_sudo_runner.py`

Startup and deployment:

- `iotsploit-cli/src/iotsploit_cli/commands/django_commands.py`
- `docker/supervisord.conf`, `docker-compose.yml`, `Dockerfile`
- package metadata and relevant documentation

Touched only if Phase 3.2's dual-endpoint approach is abandoned:

- `iotsploit-django/src/iotsploit_django/tools/discovery_server.py`
- `iotsploit-cli/src/iotsploit_cli/can_live.py`
- `docker/nginx.conf`
- `ui/lib/providers/config_provider.dart`, `ui/lib/screens/tasks/components/esp32.dart`

Expected additions:

- one Django migration for fuzzer runtime state and campaign identity;
- one focused shared execution-runtime module only if the existing interaction service
  cannot own it without circular dependencies; and
- minimal high-risk regression tests required by the acceptance matrix, marked per
  `.agents/standards/testing.md`.

## Compatibility Matrix

| Capability | Local mode | Distributed mode |
|---|---|---|
| HTTP API / ORM / target management | Required | Required |
| Synchronous plugins | Required | Required |
| Asynchronous plugins | Local background thread | Celery worker |
| Interactive plugins | Dedicated local worker | Interactive Celery queue |
| Streaming plugins | Dedicated local worker | Streaming Celery queue |
| Live WebSockets | In-memory, one process, loop-marshalled | Redis, cross-process |
| Listening ports | 8888 and 9999 on one process | 8888 and 9999 on two processes |
| Fuzzer lifecycle and statistics | Local worker + SQLite | Celery + SQLite |
| Privileged non-interactive plugins | Subprocess file IPC | Subprocess file IPC |
| Client reconnect/state recovery | SQLite | SQLite |
| Multi-worker scaling | Not supported | Supported |
| Broker retries | Not applicable | Supported |
| Hard task termination | Not guaranteed | Supported |
| Resume running work after host restart | Not supported | Existing Celery behavior |

## Testing Matrix

Per `.agents/standards/testing.md`, new tests are justified only by an uncovered
high-risk regression path. Every new file declares its `pytestmark`. Anything needing
Redis is `service`-marked and therefore outside the commit gate.

### Local mode, Redis absent

- Django imports and boots when `redis`, `celery`, and `channels_redis` cannot be imported.
- CLI `--runserver` starts ASGI and MCP without Redis preflight or Celery workers, on both
  8888 and 9999.
- A synchronous plugin returns its existing inline result.
- A non-interactive async plugin returns immediately, progresses, and completes.
- An interactive plugin asks multiple questions and completes after answers.
- Cancellation closes a pending prompt and a cooperative long-running plugin exits.
- A streaming plugin sends data and cleans up its channel.
- **Sustained cross-thread delivery:** a worker thread emitting several hundred events is
  received in order and without loss. This is the test that catches Fact 12; a
  single-event smoke test passes on broken code.
- Reconnecting a WebSocket client recovers the execution from SQLite.
- Fuzzer start/status/statistics/pause/reset/stop work.
- **Two consecutive campaigns keep separate runtime state** (Fact 13).
- A privileged plugin returns valid JSON even when it prints to stdout or invokes an
  external binary (Fact 19 / Phase 6).
- Restarting the ASGI process marks abandoned local work honestly.

### Distributed mode, Redis present — `pytest -m service`, outside the gate

- Standard, interactive, and streaming queues consume the correct jobs.
- Celery result transport is no longer the source of API status/result truth.
- Worker-to-ASGI execution events and stream data cross processes.
- Fuzzer state remains consistent between HTTP and worker processes.
- Revoke/terminate behavior remains available.
- Existing API and WebSocket envelopes remain compatible, except the Phase 2.7 decision.

### Hardware rig, both modes

- Fuzzer campaign against real CAN, confirming a single adapter construction.
- Privileged plugin result IPC.
- Streaming CAN capture over the single local ASGI process.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| In-memory Channels used across two processes | Silent loss of live events | Enforce one ASGI process in local mode |
| **Cross-thread sends into the in-memory layer (Fact 12)** | **Delayed or lost events, racing dicts; fails silently** | **Marshal every local emit onto the captured ASGI loop; test under sustained load, not one event** |
| **Fuzzer campaign rows recycled by name (Fact 13)** | **Run N+1 overwrites run N's state once it leaves Redis** | **Key on `campaign_uuid` in Phase 5.1, before state moves** |
| **Duplicate adapter construction collapses into one process (Fact 14)** | **Same CAN/serial hardware opened twice** | **Resolve ownership in Phase 5.2 before relocating the loop; validate on the rig** |
| Duplicate execution during broker failure | Hardware action runs twice | No automatic runtime failover |
| Shared plugin instances are not thread-safe | Cross-run state corruption | Use execution-scoped manager/plugin instances or serialize affected queue; verify before raising concurrency |
| Local cancellation cannot kill Python threads | Task continues after UI says cancelled | Report cooperative cancellation accurately; keep hard termination in distributed mode |
| SQLite write contention from fuzzer updates | Delayed status writes | Keep update cadence bounded and transactions short; measure before adding caching |
| Optional imports still leak through package initialization | Local install fails at import time | Test in an environment without distributed extras |
| Local-process restart leaves stale rows | UI shows work that no longer exists | Reconcile queued/running local rows at startup |
| Privileged plugin writes to fd 1 | Corrupted result document | Use a result file, not a stdout contract (Phase 6.1) |
| Gate passes while distributed mode is broken | Regression ships unnoticed | `service` tests are outside the gate by policy; run `-m service` explicitly each phase |
| Distributed behavior regresses during consolidation | Production queue failure | Keep thin Celery adapters and run the distributed suite after every phase |
| Scope overlaps interactive execution work | Conflicting lifecycle changes | Extend its existing database owner and coordinate before editing overlapping files |

The port/topology risk from the previous revision is retired by Phase 3.2, which keeps
both ports on one process instead of migrating them.

## Cost

| Workstream | Estimate |
|---|---:|
| Runtime configuration and composition wiring | 0.5–1 day |
| Unified durable execution and local workers | 2–3 days |
| Fuzzer identity, database state, and local runner | 2.5–3.5 days |
| Channels, thread-to-loop marshalling, and single-ASGI startup | 1–1.5 days |
| Privileged IPC and optional packaging/deployment | 1–1.5 days |
| Focused tests, full gate, hardware validation, documentation | 2–3 days |
| **Total** | **9–13 engineering days** |

The monetary implementation cost is `72–104 hours × engineering hourly rate`.

Changes from the previous revision: fuzzer work rose by one day for campaign identity and
duplicate adapter resolution; the Channels workstream absorbed thread-to-loop marshalling
but shed the port migration, so it held roughly flat.

If local mode must add hard process termination and automatic execution resumption after
restart, treat that as a separate 3–5 day design increment rather than silently expanding
this plan.

## Acceptance Criteria

The plan is complete only when all of the following are true:

- Local mode starts and remains usable with nothing listening on port 6379.
- Local mode works without the `redis`, `celery`, and `channels_redis` packages installed.
- No local startup path imports or contacts a distributed-only adapter.
- Adapter selection happens only in the two composition roots; `use_celery` is gone.
- All currently working plugin categories execute: sync, async, interactive, streaming,
  and non-interactive privileged.
- Live events emitted from local worker threads arrive promptly, in order, and without
  loss under sustained load.
- Fuzzer campaign lifecycle and live statistics work without Redis, two consecutive
  campaigns keep separate state, and hardware adapters are constructed once per campaign.
- HTTP and WebSocket functionality share one ASGI process in local mode, on both existing
  ports, with no change required to discovery, Nginx, the CLI, or the Flutter client.
- SQLite is the source of truth for plugin execution and fuzzer campaign state in both
  modes.
- Distributed mode still supports multiple processes, all three Celery queues, Redis
  Channels, retries, and task termination.
- Redis failure in distributed mode produces a clear infrastructure error and never
  implicitly re-executes work locally.
- Existing public HTTP/WebSocket paths and payloads remain compatible, except the
  `/ws/exploit/` decision recorded in Phase 2.7.
- Every row of the Deletion Inventory is deleted, not disabled or left as a fallback.
- Focused local tests pass, and `poetry run pytest -m service` passes with Redis running.
- `tools/testing/test-python-full.sh` passes with counts reported, apart from any
  separately documented pre-existing failure.
- Hardware-dependent streaming, fuzzer, and privileged paths are validated on the rig.

## Revision Notes

Revised 2026-09-01 after reviewing the plan against the tree. The architecture decision,
mode table, source-of-truth rule, and no-failover stance were unchanged. What changed:

- Added the Governing Standards section, because `.agents/standards/testing.md` excludes
  `service` tests from the gate — which the previous Phase 8 assumed it covered.
- Added Facts 11-19, nine defects confirmed in the code that phases now depend on or
  delete.
- Added the thread-to-loop rule and its risk row (Fact 12), previously a one-line
  "verify" step in Phase 3.
- Reordered Phase 5 so campaign identity and adapter ownership are fixed before state
  migrates onto the row.
- Replaced Phase 3's port migration with Daphne dual-endpoint binding, verified against
  the pinned Daphne, removing changes to five consumers and one risk row.
- Replaced Phase 6's stdout contract with a result file, because `redirect_stdout` does
  not cover file descriptor 1.
- Added the Deletion Inventory to satisfy `AGENTS.md`'s Delete > Replace > Add hierarchy.
- Expanded Expected File Impact with eleven owners the previous revision omitted.
- Raised the estimate from 8–12 to 9–13 days.

## Implementation Record

Implemented on `feat/optional-redis-runtime` on 2026-09-01.

- Local startup was verified while imports of `redis`, `celery`, and
  `channels_redis` were forced to fail.
- Local durable threaded execution, UUID-owned fuzzer state, result-file sudo
  IPC, and 100 ordered worker-thread Channel events have focused coverage.
- Local and distributed Django checks, migration drift, Poetry metadata, and
  both default/distributed Compose configurations passed.
- A temporary Redis-backed Celery worker processed verification tasks from the
  `celery`, `interactive`, and `streaming` queues. Redis Channels also completed
  a group round-trip and the Celery broker connection succeeded.
- `tools/testing/test-python-full.sh`: **1,102 passed, 0 failed, 0 skipped,
  42 warnings**; Ruff passed.
- `poetry run pytest -m service` currently selects zero tests and exits 5. The
  direct distributed checks above cover the available software paths, but the
  repository still needs a provisioned service suite.

The file remains in `active/` because no authorized hardware target was
selected for CAN/serial fuzzer, streaming, or root-plugin execution. Those rig
checks are the only unmet acceptance item; move this plan to `completed/` after
they pass.

## Implementation Authorization

The architecture decision and implementation are approved. Implementation started on
branch `feat/optional-redis-runtime` on 2026-09-01.
