# iotsploit-django

`iotsploit-django` is IoTSploit's Django outer ring: HTTP/WebSocket APIs, ORM,
and composition of `iotsploit-core` and `iotsploit-fuzzer`.

Local mode is the default:

```bash
IOTSPLOIT_RUNTIME=local python -m daphne \
  -e tcp:8888:interface=0.0.0.0 \
  -e tcp:9999:interface=0.0.0.0 \
  iotsploit_django.asgi:application
```

It uses SQLite for durable execution and fuzzer state, a single ASGI process, and
bounded thread pools. Redis and Celery are not installed or started.

Distributed mode keeps Redis-backed Channels and Celery workers:

```bash
pip install 'iotsploit-django[distributed]'
IOTSPLOIT_RUNTIME=distributed celery \
  -A iotsploit_django.tasks.celery_app:app worker --loglevel=info
```

Start workers for the default (`celery`), `interactive`, and `streaming` queues.
Both modes use the same SQLite records as the source of truth; changing modes
requires a process restart and `python manage.py migrate` after upgrades.
All processes in distributed mode must use the same database path. Containers
set `IOTSPLOIT_DATABASE_PATH=/app/data/db.sqlite3` on their shared data volume.
