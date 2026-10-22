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
