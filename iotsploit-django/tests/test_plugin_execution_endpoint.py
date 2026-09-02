"""POST /api/execute_plugin/ lifecycle and target-selection behavior.

The target-selection half exists because of a race that only shows up with two
clients. The endpoint acts on a process-global "current target", and when
nothing is selected it picks the first vehicle and *sets* it -- so one client's
plugin run silently changes which target another client is looking at. An
optional explicit `target_id` removes that for callers who can supply one, and
these tests pin down that supplying it neither reads nor writes the global
selection, while omitting it keeps every existing caller working exactly as
before.
"""

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
from iotsploit_django.adapters.django.interaction.runtime import execution_queue  # noqa: E402

pytestmark = pytest.mark.contract


class FakeTargetManager:
    """Records every touch of the current target, because the point of the
    explicit path is that it performs none."""

    def __init__(self, target=None, stored=None):
        self.target = target
        self.stored = stored or {}
        self.set_calls = []
        self.get_current_calls = 0
        self.get_all_calls = 0

    def get_current_target(self):
        self.get_current_calls += 1
        return self.target

    def set_current_target(self, target):
        self.set_calls.append(target)
        self.target = target

    def get_all_targets(self):
        self.get_all_calls += 1
        return list(self.stored.values())

    def get_target(self, target_id):
        return self.stored.get(target_id)

    def create_target_instance(self, data):
        return BuiltTarget(data)


class BuiltTarget:
    """Stands in for a hydrated Vehicle without needing the ORM."""

    def __init__(self, data):
        self.data = data
        self.target_id = data.get("target_id")
        self.name = data.get("name")
        self.type = data.get("type", "vehicle")


def bench(target_id="bench_vehicle", **extra):
    return {"target_id": target_id, "name": target_id, "type": "vehicle", **extra}


def post(payload):
    return RequestFactory().post(
        "/api/execute_plugin/",
        data=json.dumps(payload),
        content_type="application/json",
    )


def wire(monkeypatch, target_manager, plugin_manager=None):
    plugin_manager = plugin_manager or FakePluginManager()
    monkeypatch.setattr(
        views.TargetManager, "get_instance", staticmethod(lambda: target_manager)
    )
    monkeypatch.setattr(views, "get_exploit_plugin_manager", lambda: plugin_manager)
    return plugin_manager


class FakePluginManager:
    def __init__(self):
        self.initialize_calls = 0
        self.execution = None

    def initialize(self):
        self.initialize_calls += 1

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


# ── explicit target selection ─────────────────────────────────────────


def test_an_explicit_target_id_resolves_that_exact_target(monkeypatch):
    manager = FakeTargetManager(stored={"bench_vehicle": bench()})
    plugins = wire(monkeypatch, manager)

    response = views.execute_plugin(
        post({"plugin_name": "CAN Frame Composer", "target_id": "bench_vehicle"})
    )

    assert response.status_code == 200
    _, target, _ = plugins.execution
    assert target.target_id == "bench_vehicle"


def test_an_explicit_target_does_not_become_the_current_target(monkeypatch):
    """The race this whole path exists to remove."""
    manager = FakeTargetManager(stored={"bench_vehicle": bench()})
    wire(monkeypatch, manager)

    views.execute_plugin(
        post({"plugin_name": "CAN Frame Composer", "target_id": "bench_vehicle"})
    )

    assert manager.set_calls == []


def test_an_explicit_target_runs_with_no_current_target_set_at_all(monkeypatch):
    """The case an added lookup alone would not have fixed: with nothing
    selected, the legacy block auto-selects the first vehicle and sets it. The
    explicit path has to branch before that, not after."""
    manager = FakeTargetManager(
        target=None, stored={"bench_vehicle": bench(), "other": bench("other")}
    )
    plugins = wire(monkeypatch, manager)

    response = views.execute_plugin(
        post({"plugin_name": "CAN Frame Composer", "target_id": "bench_vehicle"})
    )

    assert response.status_code == 200
    assert manager.set_calls == []
    assert manager.target is None
    assert plugins.execution[1].target_id == "bench_vehicle"


def test_an_explicit_target_wins_over_a_different_current_target(monkeypatch):
    manager = FakeTargetManager(
        target=BuiltTarget(bench("currently_selected")),
        stored={"bench_vehicle": bench()},
    )
    plugins = wire(monkeypatch, manager)

    views.execute_plugin(
        post({"plugin_name": "CAN Frame Composer", "target_id": "bench_vehicle"})
    )

    assert plugins.execution[1].target_id == "bench_vehicle"
    assert manager.target.target_id == "currently_selected"


def test_an_unknown_target_id_is_404_and_runs_no_plugin(monkeypatch):
    """Not a fallback to the current target: a caller that named a target it
    cannot have meant something specific, and guessing would act on the wrong
    vehicle."""
    manager = FakeTargetManager(target=BuiltTarget(bench()), stored={})
    plugins = wire(monkeypatch, manager)

    response = views.execute_plugin(
        post({"plugin_name": "CAN Frame Composer", "target_id": "ghost"})
    )

    assert response.status_code == 404
    assert plugins.execution is None
    assert manager.set_calls == []


# ── the legacy path is untouched ──────────────────────────────────────


def test_omitting_the_target_id_still_uses_the_current_target(monkeypatch):
    selected = BuiltTarget(bench("currently_selected"))
    manager = FakeTargetManager(target=selected, stored={"bench_vehicle": bench()})
    plugins = wire(monkeypatch, manager)

    views.execute_plugin(post({"plugin_name": "SOME/IP Service Discovery"}))

    assert plugins.execution[1] is selected


def test_omitting_the_target_id_still_auto_selects_when_nothing_is_current(monkeypatch):
    """Existing clients depend on this, so it stays -- it is only bypassed when
    a caller names its own target."""
    manager = FakeTargetManager(target=None, stored={"bench_vehicle": bench()})
    plugins = wire(monkeypatch, manager)

    response = views.execute_plugin(post({"plugin_name": "SOME/IP Service Discovery"}))

    assert response.status_code == 200
    assert len(manager.set_calls) == 1
    assert plugins.execution[1].target_id == "bench_vehicle"


def test_an_empty_target_id_falls_back_rather_than_404ing(monkeypatch):
    """A client sending "" means "I did not choose", not "target named empty"."""
    selected = BuiltTarget(bench("currently_selected"))
    manager = FakeTargetManager(target=selected, stored={})
    plugins = wire(monkeypatch, manager)

    response = views.execute_plugin(
        post({"plugin_name": "SOME/IP Service Discovery", "target_id": ""})
    )

    assert response.status_code == 200
    assert plugins.execution[1] is selected


# ── long-running durable executions ──────────────────────────────────


def test_monitor_mode_uses_the_streaming_queue():
    parameters = {"request": {"schema_version": 1, "mode": "monitor"}}

    assert execution_queue("CAN Live Capture", parameters) == "streaming"


def test_explicit_capture_uses_the_standard_queue():
    parameters = {"request": {"schema_version": 1, "mode": "capture"}}

    assert execution_queue("CAN Live Capture", parameters) == "celery"


@pytest.mark.parametrize(
    "plugin_name, request_payload",
    [
        ("CAN Live Capture", "not json"),
        ("Interactive Demo", {"mode": "monitor"}),
    ],
)
def test_malformed_or_other_interactive_runs_stay_on_the_interactive_queue(
    plugin_name, request_payload
):
    assert execution_queue(
        plugin_name, {"request": request_payload}
    ) == "interactive"
