"""Durable workers wire process-local stream adapters before plugin execution."""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.tasks import interaction_tasks  # noqa: E402

pytestmark = pytest.mark.contract


def test_execution_worker_configures_its_stream_backend(monkeypatch):
    calls = []
    monkeypatch.setattr(
        interaction_tasks,
        "ensure_stream_backend_configured",
        lambda: calls.append("configured"),
    )

    interaction_tasks._ensure_execution_runtime()

    assert calls == ["configured"]
