"""Durable workers wire process-local stream adapters before plugin execution."""

from __future__ import annotations

import os
import time

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.adapters.django.interaction import runtime  # noqa: E402
from iotsploit_django.adapters.django.interaction.models import PluginExecution  # noqa: E402
from iotsploit_django.adapters.memory import task_runner  # noqa: E402

pytestmark = pytest.mark.contract


def test_execution_worker_configures_its_stream_backend(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "iotsploit_django.composition_root.core_container.configure_stream_backend",
        lambda: calls.append("configured"),
    )

    runtime.configure_execution_runtime()

    assert calls == ["configured"]


def test_local_runner_completes_the_durable_execution(monkeypatch, django_test_database):
    class Manager:
        def run_plugin_in_process(self, plugin_name, target, parameters):
            return {"status": "success", "data": parameters}, {"source": plugin_name}

    monkeypatch.setattr(
        "iotsploit_django.composition_root.core_container.build_exploit_plugin_manager",
        lambda: Manager(),
    )
    monkeypatch.setattr(
        "iotsploit_django.composition_root.core_container.configure_stream_backend",
        lambda: None,
    )
    monkeypatch.setattr(task_runner, "_reconciled", True)

    submitted = task_runner.InProcessTaskRunner().submit(
        "Example", target=None, parameters={"value": 7}
    )

    deadline = time.monotonic() + 5
    execution = None
    while time.monotonic() < deadline:
        execution = PluginExecution.objects.get(execution_id=submitted["execution_id"])
        if execution.is_terminal:
            break
        time.sleep(0.02)

    assert execution.status == "completed"
    assert execution.result == {
        "status": "success",
        "data": {"value": 7},
        "source": "Example",
    }
    PluginExecution.objects.all().delete()


def test_replay_startup_failure_is_replayed_to_a_late_execution_subscriber(monkeypatch, django_test_database, tmp_path):
    import asyncio
    from channels.layers import channel_layers
    from channels.routing import URLRouter
    from channels.testing import WebsocketCommunicator
    from django.urls import re_path
    from iotsploit_exploits.canbus.live_capture import CanLiveCapturePlugin
    from iotsploit_django.adapters.django.interaction import service
    from iotsploit_django.adapters.django.threadsafe_channel_layer import ThreadSafeInMemoryChannelLayer
    from iotsploit_django.websocket.consumers_impl import PluginExecutionConsumer

    class Manager:
        def run_plugin_in_process(self, plugin_name, target, parameters):
            target_map = {"buses": [{"bus_id": "body", "name": "Body CAN", "type": "can",
                                     "properties": {"messages": []}}], "components": []}
            return CanLiveCapturePlugin().execute(target_map, parameters), {}

    monkeypatch.setattr("iotsploit_django.composition_root.core_container.build_exploit_plugin_manager", lambda: Manager())
    monkeypatch.setattr(runtime, "configure_execution_runtime", lambda: None)
    monkeypatch.setattr(service, "emit", lambda *args, **kwargs: None)
    monkeypatch.setitem(channel_layers.backends, "default", ThreadSafeInMemoryChannelLayer())
    parameters = {"request": {"schema_version": 1, "bus_id": "body", "mode": "replay",
                              "transport": {"interface": "file", "path": str(tmp_path / "deleted.asc")}}}
    execution = service.create_execution("CAN Live Capture", parameters=parameters)
    try:
        runtime.run_execution(execution.execution_id, "CAN Live Capture", parameters=parameters)

        async def read_state():
            app = URLRouter([re_path(r"^execution/(?P<execution_id>[^/]+)/$", PluginExecutionConsumer.as_asgi())])
            socket = WebsocketCommunicator(app, f"/execution/{execution.execution_id}/")
            connected, _ = await socket.connect()
            assert connected
            state = await socket.receive_json_from()
            await socket.disconnect()
            return state

        event = asyncio.run(read_state())

        assert event["event"] == "state"
        assert event["payload"]["status"] == "completed"
        assert event["payload"]["result"]["status"] == "error"
        assert "deleted.asc" in event["payload"]["result"]["message"]
    finally:
        execution.delete()


def test_cancelled_queued_replay_is_not_restarted_by_a_late_worker(monkeypatch, django_test_database):
    from iotsploit_django.adapters.django.interaction import service

    def must_not_start():
        raise AssertionError("a cancelled execution started plugin work")

    monkeypatch.setattr("iotsploit_django.composition_root.core_container.build_exploit_plugin_manager", must_not_start)
    monkeypatch.setattr(service, "emit", lambda *args, **kwargs: None)
    execution = service.create_execution("CAN Live Capture")
    try:
        assert service.cancel_execution(execution.execution_id)

        result = runtime.run_execution(execution.execution_id, "CAN Live Capture")
        execution.refresh_from_db()

        assert result["status"] == "cancelled"
        assert execution.status == "cancelled"
        assert execution.started_at is None
    finally:
        execution.delete()
