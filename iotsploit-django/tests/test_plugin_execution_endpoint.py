"""POST /api/execute_plugin/ lifecycle behavior."""

from __future__ import annotations

import json
import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.test import RequestFactory  # noqa: E402

import iotsploit_django.view_handlers.plugin_views as views  # noqa: E402

pytestmark = pytest.mark.contract


class FakeTargetManager:
    def __init__(self, target):
        self.target = target

    def get_current_target(self):
        return self.target


class FakePluginManager:
    def __init__(self):
        self.initialize_calls = 0
        self.execution = None

    def initialize(self):
        self.initialize_calls += 1

    def get_plugin_info(self, plugin_name):
        return {"Name": plugin_name, "RequiresRoot": False}

    def execute_plugin(self, plugin_name, target=None, parameters=None):
        self.execution = (plugin_name, target, parameters)
        return {"success": True}


def test_execute_plugin_does_not_broadcast_initialize(monkeypatch):
    target = object()
    target_manager = FakeTargetManager(target)
    plugin_manager = FakePluginManager()
    monkeypatch.setattr(
        views.TargetManager,
        "get_instance",
        staticmethod(lambda: target_manager),
    )
    monkeypatch.setattr(views, "get_exploit_plugin_manager", lambda: plugin_manager)
    request = RequestFactory().post(
        "/api/execute_plugin/",
        data=json.dumps(
            {
                "plugin_name": "SOME/IP Service Discovery",
                "parameters": {"mode": "find", "host": "10.8.0.10"},
            }
        ),
        content_type="application/json",
    )

    response = views.execute_plugin(request)

    assert response.status_code == 200
    assert plugin_manager.initialize_calls == 0
    assert plugin_manager.execution == (
        "SOME/IP Service Discovery",
        target,
        {"mode": "find", "host": "10.8.0.10"},
    )
