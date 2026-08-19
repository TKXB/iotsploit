# Proposal: Remove the Redis dependency (lightweight mode)

Companion to [`redis_decoupling_analysis.md`](./redis_decoupling_analysis.md).

## Goal

Make the stack runnable **without a Redis server** by default, so the project is lighter
and has fewer required dependencies. This fits the `iotsploit-lightweight` direction.

## Verdict

Reasonable and recommended. For a local, single-operator security tool with light
queueing needs, Redis is overkill. The catch: it is a **real (if modest) refactor**, not a
config flip — see "State of the seam" below.

## Why Redis is here at all

Redis exists for **one architectural reason: multiple processes** — Django ASGI + a
separate Celery worker + the sudo subprocess. Redis is the glue between them (task queue,
cross-process pub/sub, shared state). Drop the multi-process requirement and every Redis
use gets a stdlib-level replacement.

## State of the seam (important caveat)

The decoupling seam is more hollow than it first appears:

- The `TaskRunner` port exists (`submit()`), but `InProcessTaskRunner`
  (`adapters/memory/task_runner.py`) is a **stub** — it returns a dict describing the
  execution and never actually runs the plugin.
- The real HTTP flow in `web/views.py` **bypasses the port** — it calls
  `execute_plugin_task.delay()` and polls `AsyncResult` directly.

So `use_celery=False` does **not** run plugins end-to-end today. Removing Redis requires
implementing the in-process path for real, not just flipping the flag.

## The one commitment

Going Redis-free = committing to **single-process, single-ASGI-worker**. Consequences to
accept (all fine for a locally-run tool):

- `InMemoryChannelLayer` shares WebSocket groups only within one process — so no
  `gunicorn --workers 4`.
- In-memory task/campaign state is lost on restart (fine for ephemeral pentest runs).
- Long-running plugins must run in a thread, or they block the ASGI event loop — the one
  place to be careful.

These only matter for a scaled multi-user deployment, which this is not.

## Replacements per Redis use

| Redis is used for | Lightweight replacement | Effort |
|---|---|---|
| Celery task queue/results | Run plugin in a background **thread** + in-memory `{task_id: status}` registry for status/revoke | Moderate |
| Channels WebSocket pub/sub | `InMemoryChannelLayer` (built into `channels`, zero Redis) — config change | Trivial |
| Fuzzer campaign state | In-memory dict, or reuse the existing **SQLite** (`db.sqlite3`) | Low–moderate |
| Sudo result IPC (`privilege_mgr` ↔ `plugin_sudo_runner`) | Temp file with restricted perms, or read subprocess **stdout** | Low |

## Recommended approach: lightweight by default, Redis as optional extra

Do **not** delete the working Celery/Redis path. Instead:

1. **Implement the in-process path for real** — thread-based execution + status/revoke
   registry in `InProcessTaskRunner`. Route `web/views.py` and
   `cli/.../plugin_commands.py` through the `TaskRunner` port instead of calling Celery
   (`.delay` / `AsyncResult`) directly.
2. **Swap `CHANNEL_LAYERS` to `InMemoryChannelLayer`** as the default in
   `settings/base.py`; replace the sudo-IPC Redis handoff with a temp file / stdout pipe.
3. **Move `redis` / `celery` / `channels_redis` out of core dependencies** into an optional
   `[celery]` extra in `pyproject.toml`. Default install → no Redis, runs single-process.
   Users who want multi-process scaling install the extra and set `use_celery=True`.

This yields the lighter footprint (no Redis server, fewer required deps) without discarding
a working execution mode or foreclosing future scaling.

## Suggested order of work

1. Real thread-based `InProcessTaskRunner` (status + revoke); route the two leaking call
   sites (`web/views.py`, `plugin_commands.py`) through the port. — highest value, unblocks
   Redis-free execution.
2. `InMemoryChannelLayer` default + sudo-IPC temp-file handoff.
3. Fuzzer campaign store → in-memory / SQLite. (Feature-specific; do last.)
4. Dependency split: move `redis`/`celery`/`channels_redis` to an optional extra.

Steps 1–2 make the normal path Redis-free. Steps 3–4 complete the removal. Rough estimate:
a focused day of work, most of it in step 1.
