"""Distributed mode still works when Redis is the transport.

Local mode is covered by the rest of the suite; nothing there exercises the
Redis broker or the Redis channel layer, so a change that quietly broke
multi-process operation would ship green. These tests provision that
dependency the way ``conftest.py`` provisions the ORM: they run for real
against a live Redis and skip with a reason when there isn't one, so the
commit gate stays honest on a machine that has no Redis installed.

Redis logical database 15 is treated as scratch space. Published messages are
consumed back off the queue by the assertion itself, so a run leaves the
broker as it found it.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

import pytest

pytestmark = [pytest.mark.service, pytest.mark.integration]

TEST_REDIS_DB = 15
RUN_EXECUTION_TASK = "iotsploit_django.tasks.interaction_tasks.run_execution_task"


def _redis_endpoint():
    from django.conf import settings

    return (
        getattr(settings, "REDIS_HOST", "127.0.0.1"),
        int(getattr(settings, "REDIS_PORT", 6379)),
    )


@pytest.fixture(scope="session")
def redis_url():
    """A reachable Redis, or the reason this test could not run."""
    import django
    from django.apps import apps

    if not apps.ready:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
        django.setup()

    host, port = _redis_endpoint()
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"no Redis at {host}:{port} ({exc}); distributed mode not exercised")
    return f"redis://{host}:{port}/{TEST_REDIS_DB}"


@pytest.fixture
def redis_client(redis_url):
    import redis

    client = redis.Redis.from_url(redis_url)
    yield client
    client.close()


@pytest.fixture
def celery_on_test_redis(redis_url):
    """Point the configured Celery app at the scratch database for one test."""
    from iotsploit_django.tasks.celery_app import app

    previous = (app.conf.broker_url, app.conf.result_backend)
    app.conf.broker_url = redis_url
    app.conf.result_backend = redis_url
    try:
        yield app
    finally:
        app.conf.broker_url, app.conf.result_backend = previous
        import redis

        client = redis.Redis.from_url(redis_url)
        # kombu declares an exchange binding per queue it publishes to.
        client.delete("_kombu.binding.interactive", "_kombu.binding.streaming")
        client.close()


def _consume(redis_client, queue):
    """Pop one published message, leaving the queue as we found it."""
    raw = redis_client.rpop(queue)
    assert raw is not None, f"nothing was published to the {queue!r} queue"
    envelope = json.loads(raw)
    body = json.loads(base64.b64decode(envelope["body"]).decode())
    return envelope["headers"], body


# ── Broker ───────────────────────────────────────────────────────────

def test_interactive_run_is_published_to_the_interactive_queue(
    db, redis_client, celery_on_test_redis
):
    from iotsploit_django.adapters.django.task_runner import CeleryTaskRunner

    result = CeleryTaskRunner().submit(
        "Interactive Demo", None, {}, context={"interactive": True}
    )

    headers, body = _consume(redis_client, "interactive")
    args, _kwargs, _embed = body
    assert headers["task"] == RUN_EXECUTION_TASK
    assert args[0] == result["execution_id"]
    assert result["execution_type"] == "interactive"


def test_streaming_monitor_request_is_published_to_the_streaming_queue(
    db, redis_client, celery_on_test_redis
):
    from iotsploit_django.adapters.django.task_runner import CeleryTaskRunner

    CeleryTaskRunner().submit(
        "CAN Live Capture",
        None,
        {"request": {"mode": "monitor"}},
        context={"interactive": True},
    )

    headers, _body = _consume(redis_client, "streaming")
    assert headers["task"] == RUN_EXECUTION_TASK


def test_the_durable_row_exists_before_the_broker_is_told(
    db, redis_client, celery_on_test_redis
):
    """SQLite owns the run. A crash after publishing must not lose it."""
    from iotsploit_django.adapters.django.interaction.models import PluginExecution
    from iotsploit_django.adapters.django.task_runner import CeleryTaskRunner

    result = CeleryTaskRunner().submit(
        "Interactive Demo", None, {}, context={"interactive": True}
    )
    _consume(redis_client, "interactive")

    row = PluginExecution.objects.get(execution_id=result["execution_id"])
    assert row.status == "queued"
    assert row.celery_task_id, "the Celery task id was never recorded on the row"
    assert result["task_id"] == result["execution_id"], (
        "the public handle must stay the durable id, not Celery's"
    )


def test_a_broker_failure_marks_the_row_failed_instead_of_losing_it(db, monkeypatch):
    """No silent 'started' when the broker is unreachable.

    The dispatch target is replaced wholesale rather than patching the task's
    `apply_async`: `run_execution_task` is a `shared_task` proxy, and patching
    through it only binds to the configured app once something else has
    finalised it -- run alone, the proxy resolves to Celery's default AMQP app
    and the test dials a broker it never meant to touch.
    """
    from iotsploit_django.adapters.django.interaction.models import PluginExecution
    from iotsploit_django.adapters.django.task_runner import CeleryTaskRunner
    from iotsploit_django.tasks import interaction_tasks

    class RefusingTask:
        def apply_async(self, *args, **kwargs):
            raise OSError("broker unreachable")

    monkeypatch.setattr(interaction_tasks, "run_execution_task", RefusingTask())

    with pytest.raises(OSError):
        CeleryTaskRunner().submit(
            "Interactive Demo", None, {}, context={"interactive": True}
        )

    row = PluginExecution.objects.latest("created_at")
    assert row.status == "failed"
    assert row.error["reason"] == "dispatch_failed"


# ── Channel layer ────────────────────────────────────────────────────

def test_redis_layer_delivers_between_two_independent_instances(redis_url):
    """Two layer objects stand in for the worker process and the ASGI process."""
    import asyncio

    from channels_redis.core import RedisChannelLayer

    async def exercise():
        producer = RedisChannelLayer(hosts=[redis_url])
        consumer = RedisChannelLayer(hosts=[redis_url])
        group = f"execution_{uuid.uuid4().hex}"
        channel = await consumer.new_channel()
        await consumer.group_add(group, channel)
        try:
            await producer.group_send(group, {"type": "execution_event", "seq": 1})
            return await asyncio.wait_for(consumer.receive(channel), timeout=5)
        finally:
            await producer.flush()
            await consumer.flush()

    assert asyncio.run(exercise())["seq"] == 1


def test_send_group_reaches_a_redis_layer_from_synchronous_code(redis_url):
    """`send_group` must take the async_to_sync branch for a Redis layer.

    The Redis layer has no `group_send_threadsafe`, so the helper has to fall
    through to the distributed path. Getting this wrong silently drops every
    event a worker emits.
    """
    import asyncio

    from channels_redis.core import RedisChannelLayer

    from iotsploit_django.adapters.django.threadsafe_channel_layer import send_group

    layer = RedisChannelLayer(hosts=[redis_url])
    assert not hasattr(layer, "group_send_threadsafe")
    group = f"execution_{uuid.uuid4().hex}"

    async def subscribe():
        channel = await layer.new_channel()
        await layer.group_add(group, channel)
        return channel

    channel = asyncio.run(subscribe())
    send_group(layer, group, {"type": "execution_event", "seq": 7})

    async def collect():
        try:
            return await asyncio.wait_for(layer.receive(channel), timeout=5)
        finally:
            await layer.flush()

    assert asyncio.run(collect())["seq"] == 7


# ── Settings ─────────────────────────────────────────────────────────

def test_distributed_settings_select_redis_broker_and_channel_layer():
    """The mode switch is what puts Redis back; assert it in a clean process."""
    script = r'''
import os
os.environ["IOTSPLOIT_RUNTIME"] = "distributed"
os.environ["DJANGO_SETTINGS_MODULE"] = "iotsploit_django.settings.dev"
import django
django.setup()
from django.conf import settings

assert settings.IOTSPLOIT_RUNTIME == "distributed", settings.IOTSPLOIT_RUNTIME
backend = settings.CHANNEL_LAYERS["default"]["BACKEND"]
assert backend == "channels_redis.core.RedisChannelLayer", backend
assert settings.CELERY_BROKER_URL.startswith("redis://"), settings.CELERY_BROKER_URL
assert settings.CELERY_RESULT_BACKEND.startswith("redis://")
'''
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("IOTSPLOIT_RUNTIME", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(project_root / "iotsploit-django" / "src"),
            str(project_root / "iotsploit-core" / "src"),
            str(project_root / "iotsploit-protocols" / "src"),
            env.get("PYTHONPATH", ""),
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr
