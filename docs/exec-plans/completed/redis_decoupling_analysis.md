# Redis Decoupling Analysis (iotsploit-*)

Goal: reduce reliance on Redis so the stack can run "lightweight" (ideally without a
Redis server for the normal path).

Key finding up front: **all Redis reliance lives in one package, `iotsploit-django`**
(plus two soft touches in the CLI). `iotsploit-core` and the other packages are already
clean. Two of the three reliance types already have a decoupling seam:

- **Celery** is behind a `TaskRunner` port with an `InProcessTaskRunner` fallback
  (`get_exploit_plugin_manager(use_celery=False)`).
- **Streaming** is behind a `StreamManager` Protocol (`iotsploit-core/.../ports/stream_backend.py`).

## Reliance inventory

### A. Direct Redis client (`redis.Redis`) — real key/value state

| Package | File | Function / symbol | What Redis does | Coupling |
|---|---|---|---|---|
| django | `tools/iot_fuzzer_manager.py` | `__init__`, `_store/_get/_update/_remove_campaign_state`, `get_active_campaigns`, `_calculate_final_statistics_from_redis` (+ all `*_campaign` methods depend on them) | Sole store of fuzzing-campaign state, shared Django↔Celery worker | Hard |
| django | `adapters/django/stream_manager.py` | `DjangoStreamManager.__init__`, `register_stream`, `unregister_stream`, `broadcast_data`, `stop_broadcast`, `get_active_channels`, `get_broadcast_channels` | Redis sets tracking active/broadcast channels | Hard (but behind `StreamManager` port) |
| django | `tools/plugin_sudo_runner.py` | `main()` | Sudo subprocess writes plugin result to a Redis key | Hard (IPC channel) |
| django | `tools/privilege_mgr.py` | `run_plugin_with_sudo()` | Reads that result key back | Hard (paired with above) |
| cli | `commands/django_commands.py` | `_check_redis_available()`, `do_runserver()` | Preflight TCP ping + `redis.Redis().ping()` | Soft (guard only) |
| django | `web/views.py` | result-parsing branch (~434–441) | Logs/parses a Celery result (inherits Redis via backend) | Incidental |

### B. Channels layer (`channels_redis`) — WebSocket pub/sub

| Package | File | Function / symbol | What Redis does | Coupling |
|---|---|---|---|---|
| django | `websocket/consumers_impl.py` | `connect`, `disconnect`, all `group_add`/`group_discard` calls | Group membership for WS fan-out | Hard (via channel layer) |
| django | `tasks/plugin_tasks.py` | progress push (`group_send`) | Worker→browser updates | Hard |
| django | `tasks/legacy_tasks_impl.py` | multiple `group_send` sites | Worker→browser updates | Hard |
| django | `tools/iot_fuzzer_bridge.py` | `__init__`, `group_send` sites (~202–224) | Fuzzer→browser updates | Hard |
| django | `tools/xlogger.py` | log handler `group_send` (~21) | Streams logs to WS console | Soft (guarded by `if channel_layer`) |
| django | `view_handlers/console_logs_views.py` | `get_channel_layer` import/use | Console log stream | Soft |
| django | `settings/base.py` | `CHANNEL_LAYERS` | `channels_redis.core.RedisChannelLayer` config | Config |

### C. Celery (Redis broker + result backend)

| Package | File | Function / symbol | What Redis does | Coupling |
|---|---|---|---|---|
| django | `settings/base.py` | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Points broker+results at `redis://…:6379` | Config |
| django | `tasks/celery_app.py` | `app = Celery(...)` | App wiring | Config |
| django | `tasks/__init__.py`, `tasks/fuzzer_tasks.py` | shared-task app binding | Force `@shared_task` onto this app | Config |
| django | `adapters/django/task_runner.py` | `CeleryTaskRunner.run(...)` → `execute_plugin_task.delay(...)` | Dispatch plugin exec to worker | Hard, but ported |
| django | `ports_impl/task_runner.py` | re-export of `CeleryTaskRunner` | Port binding | Seam |
| django | `adapters/django/exploit_manager_factory.py` | `get_exploit_plugin_manager(use_celery=…)` | Picks `CeleryTaskRunner` vs `InProcessTaskRunner` | Seam ✅ |
| django | `composition_root/core_container.py` | `build_*(use_celery=…)` | Same switch at container level | Seam ✅ |
| django | `web/views.py` | `execute_plugin_task.delay()` (769), `AsyncResult(...).revoke()` (813) | Dispatch + revoke | Hard (leaks past port) |
| django | `tasks/fuzzer_tasks.py` / `legacy_tasks_impl.py` / `plugin_tasks.py` | `@shared_task` defs | The task bodies | Hard |
| cli | `console.py` | `use_celery = env SAT_SHELL_USE_CELERY`, `get_exploit_plugin_manager(use_celery=…)` | Toggles Celery on/off at shell start | Seam ✅ |
| cli | `commands/plugin_commands.py` | `AsyncResult(task_id, app=celery_app)` polling (~136–140) | Poll task status | Hard (leaks past port) |
| cli | `commands/django_commands.py` | `do_runserver` boots worker + Redis preflight | Starts Celery worker | Soft |

### D. Already Redis-free (the seams to build on)

- `iotsploit-core/.../core/stream_manager.py` and `ports/stream_backend.py` — define the
  `StreamManager` Protocol, no Redis import by design.
- `iotsploit-mcp`, `iotsploit-drivers`, `iotsploit-exploits`, `iotsploit-platforms`,
  `iotsploit-fuzzer` — no Redis/Celery/Channels at all.

## Recommendation: what to decouple first

**Decouple the Celery `TaskRunner` path first** — close the two places that still call
Celery directly instead of going through the existing port. Highest value for least work.

| Target | Effort | Payoff | Blocker |
|---|---|---|---|
| **Celery TaskRunner** | **Low** — seam already exists | **High** — unblocks Redis-free plugin execution | Two direct calls leak past the port |
| Channels / WebSocket | Low (config swap) | Medium | Only works once single-process (after Celery is off) |
| Fuzzer campaign store | High (new backend interface) | Low — fuzzer feature only | No abstraction exists yet |
| Sudo-result IPC | Medium | Low — sudo path only | Paired rewrite of two files |

Why Celery wins: the abstraction is already built (`use_celery=False` →
`InProcessTaskRunner`, plus the `SAT_SHELL_USE_CELERY` toggle in `console.py`). The only
reason `use_celery=False` isn't fully Redis-free today is two leaks that bypass the runner:

- `web/views.py:769` — `execute_plugin_task.delay(...)` and `:813` `AsyncResult(...).revoke()`
- `iotsploit-cli/.../plugin_commands.py:136–140` — `AsyncResult(task_id, app=celery_app)` polling

Route those through the `TaskRunner` port (add `revoke`/`status` to the interface,
implement in-process) and the main plugin-execution flow no longer needs Redis.

## Suggested sequence

1. **Celery leaks → port.** Extend `TaskRunner` with `revoke`/`status`; route
   `web/views.py` and `plugin_commands.py` through it. Unblocks Redis-free execution.
2. **Channels → `InMemoryChannelLayer`** in `settings/base.py`. One config block; only
   valid once step 1 makes it single-process, so it comes second.
3. **Leave the fuzzer store and sudo IPC as full-mode-only features**, or give them
   in-memory backends later. They're isolated, feature-specific, and heavy — don't let
   them gate the lightweight win.

Steps 1–2 together eliminate Redis for the normal path. Steps 3+ are optional and only
matter if fuzzing/sudo are needed in lightweight mode.

---

## Reassessment & Conclusion (code-verified)

After reading the actual implementations, the original recommendation above is **too
optimistic**. Key correction: the `InProcessTaskRunner` seam exists, but the in-process
implementation is a **stub** — it does not execute plugins.

### Verified state of the seam

| Symbol | File | Reality |
|---|---|---|
| `TaskRunner` Protocol | `iotsploit-core/.../ports/task_runner.py` | Only has `submit()`. **No `revoke`, no `status`.** |
| `CeleryTaskRunner.submit` | `iotsploit-django/.../adapters/django/task_runner.py` | Really calls `execute_plugin_task.delay()`; plugin runs in worker. Returns `task_id`. |
| `InProcessTaskRunner.submit` | `iotsploit-django/.../adapters/memory/task_runner.py` | **Only echoes params back** as `{execution_type: "in_process", ...}`. Plugin never runs. |

So `use_celery=False` today does **not** give Redis-free plugin execution — it gives
**silent no-op execution** for any plugin routed through the runner.

### Side effects of removing Redis from the TaskRunner path

1. **InProcessTaskRunner is a stub** — must first be made to actually call
   `plugin_instance.execute()` / `execute_async()`. Without this, plugins silently don't run.
2. **Async → sync blocking** — Celery runs in a separate worker; the HTTP request returns
   immediately with a `task_id`. In-process runs in the request/CLI thread → the request
   blocks until the plugin finishes. Long tasks (fuzzing, `duration>5`, streaming) stall.
3. **No `revoke` / `status` in the interface** — `web/views.py:813`
   `AsyncResult(task_id).revoke()` and `plugin_commands.py:162` `AsyncResult(...).ready()`
   polling have no in-process equivalent. Synchronous execution has no background task to
   revoke.
4. **Frontend contract breaks** — `views.py:776-781` returns `task_id` +
   `websocket_url: /ws/exploit/{task_id}/`. In-process mode has no `task_id`; the WebSocket
   subscription flow loses its anchor.
5. **Progress streaming disappears** — no worker process means `group_send` in
   `plugin_tasks.py` / `legacy_tasks_impl.py` has no sender. Progress reporting needs a new
   in-memory mechanism.
6. **CLI polling branch skipped** — `plugin_commands.py:145` gates on
   `execution_type == 'async'`; `in_process` falls through with no result handling.
7. **`execute_plugin_async` endpoint bypasses the runner entirely** —
   `views.py:742` calls `execute_plugin_task.delay()` directly. This is one of the two
   "leaks"; routing it through the port also requires redesigning its response shape.
8. **Result store gone** — Celery persists results in the Redis backend; `AsyncResult` reads
   them. In-process has no result store; `task_result.info` progress polling has no source.

### Removing TaskRunner Redis does NOT make the stack Redis-free

Redis is still required by three other, independent paths:

- **Channels / WebSocket** (`channels_redis`) — fan-out for browser updates.
- **Fuzzer campaign store** (`iot_fuzzer_manager.py`) — shared Django↔worker state, no
  abstraction exists yet.
- **Sudo-result IPC** (`plugin_sudo_runner.py` ↔ `privilege_mgr.py`) — paired Redis key
  channel.

So decoupling only the TaskRunner removes Redis from **one of four** places, and that one
place (async plugin execution) is where the async worker pattern adds the **most** value for
this tool's actual workloads (long fuzzing/exploit runs with live progress).

### Decision: keep both modes — do not delete the Celery path

This project is not a small app: it has long-running fuzzing campaigns, streaming exploits,
and sudo-elevated plugins that genuinely benefit from a separate worker + shared state.

| Option | Verdict |
|---|---|
| Remove Redis from TaskRunner (delete Celery path) | ❌ Not recommended — high cost (build real execution + revoke/status + progress + new response contract), payoff is only 1/4 of Redis usage, and loses a working async feature. |
| Keep Redis in TaskRunner **and** complete the InProcess fallback | ✅ Recommended — two modes coexist via the existing `use_celery` toggle. Heavy load (fuzzing/long tasks/progress) → Celery + Redis. Lightweight/CLI/debug → in-process, no Redis. |

### What "complete the InProcess fallback" actually requires

1. Make `InProcessTaskRunner.submit()` really execute the plugin (call
   `plugin_instance.execute()` / `execute_async()`), mirroring what `plugin_tasks.py:63`
   already does inside the worker (`get_exploit_plugin_manager(use_celery=False)`).
2. Add `revoke` / `status` to the `TaskRunner` Protocol; implement in-process versions
   (cancellation is the hard part for synchronous execution — likely needs a thread +
   cancel flag, or scoped to "already done / not started" semantics).
3. Handle `execution_type == 'in_process'` returns in the callers that currently only check
   `'async'`: `views.py:460`, `exploit_manager.py:611`, `adapters/django/plugins/models.py:162`,
   `plugin_commands.py:145`.
4. Redefine the `execute_plugin_async` endpoint response for the no-`task_id` case (or route
   it through the runner and let the runner decide the shape).
5. Replace Celery-backend progress polling with an in-memory progress registry / callback.
6. Only then does step 2 of the original plan (Channels → `InMemoryChannelLayer`) become
   valid, because it requires single-process operation.

### Rule of thumb (general, for choosing per-app)

- Short tasks (seconds), single user, no background needed → **in-process**; don't add Redis.
- Long tasks (minutes–hours), need responsive UI / concurrency / shared state / retries →
  **Redis + Celery**.
- IoTSploit has both → **keep both**, selected by `use_celery`.

### Bottom line

Don't "remove Redis from the task runner." Instead: **keep Celery as the default for heavy
work, and invest in making `InProcessTaskRunner` actually run plugins** so the existing
`use_celery=False` toggle becomes a real lightweight mode. This preserves the async features
the tool already uses while giving a Redis-free escape hatch for CLI/debug use.
