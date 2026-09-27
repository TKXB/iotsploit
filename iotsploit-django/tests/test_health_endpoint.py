from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import django
import pytest
from django.test import Client, override_settings


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_django.view_handlers.misc_legacy_views import API_VERSION  # noqa: E402

pytestmark = pytest.mark.contract


@override_settings(IOTSPLOIT_RUNTIME="local")
def test_health_reports_version_runtime_and_database(db):
    response = Client().get("/api/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == API_VERSION
    assert body["runtime"] == "local"
    assert body["version"]
    assert body["checks"] == {"database": "ok"}


def test_health_reports_a_failing_database_as_a_check(db, monkeypatch):
    monkeypatch.setattr(
        "iotsploit_django.view_handlers.misc_legacy_views.connection.ensure_connection",
        Mock(side_effect=RuntimeError("database is locked")),
    )

    response = Client().get("/api/health/")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "database is locked"


@override_settings(IOTSPLOIT_RUNTIME="distributed", REDIS_HOST="10.0.0.5", REDIS_PORT=6380, REDIS_DB=2)
def test_health_pings_redis_only_in_distributed_runtime(db, monkeypatch):
    client = Mock()
    client.ping.side_effect = ConnectionError("Connection refused")
    redis_class = Mock(return_value=client)
    # `redis` ships only with the distributed extra, so a fake module keeps the
    # test independent of which extras are installed.
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=redis_class))

    response = Client().get("/api/health/")

    assert response.status_code == 200
    assert response.json()["checks"] == {
        "database": "ok",
        "redis": "Connection refused",
    }
    redis_class.assert_called_once_with(host="10.0.0.5", port=6380, db=2, socket_timeout=1)


def test_health_rejects_post():
    assert Client().post("/api/health/").status_code == 405
