"""TargetManager singleton construction.

The instance used to be published before ``initialize()`` ran. On a cold start
the UI fires several requests at once, and one arriving while the first was
still creating tables got an object with no ``Session`` -- an AttributeError in
``list_targets``. These tests pin that no caller ever sees a half-built one.
"""

from __future__ import annotations

import os
import threading

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def fresh_singleton(monkeypatch):
    """Start from no instance; monkeypatch puts the real one back afterwards."""
    monkeypatch.setattr(TargetManager, "_instance", None)
    return monkeypatch


def test_concurrent_caller_waits_for_initialize_to_finish(fresh_singleton):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_initialize(self):
        calls.append(self)
        started.set()
        release.wait(timeout=5)
        self.Session = "session"

    fresh_singleton.setattr(TargetManager, "initialize", slow_initialize)
    seen = {}

    def construct(name):
        manager = TargetManager()
        seen[name] = (manager, hasattr(manager, "Session"))

    first = threading.Thread(target=construct, args=("first",))
    second = threading.Thread(target=construct, args=("second",))

    first.start()
    assert started.wait(timeout=5)
    second.start()
    second.join(timeout=0.2)
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert seen["first"] == (seen["second"][0], True)
    assert seen["second"][1] is True
    assert len(calls) == 1


def test_failed_initialize_is_not_cached(fresh_singleton):
    attempts = []

    def flaky_initialize(self):
        attempts.append(self)
        if len(attempts) == 1:
            raise RuntimeError("database is locked")
        self.Session = "session"

    fresh_singleton.setattr(TargetManager, "initialize", flaky_initialize)

    with pytest.raises(RuntimeError, match="database is locked"):
        TargetManager()
    manager = TargetManager()

    assert TargetManager._instance is manager
    assert manager.Session == "session"
    assert len(attempts) == 2


def test_later_calls_reuse_the_built_instance(fresh_singleton):
    calls = []
    fresh_singleton.setattr(TargetManager, "initialize", lambda self: calls.append(self))

    first = TargetManager()
    second = TargetManager.get_instance()

    assert first is second
    assert len(calls) == 1
