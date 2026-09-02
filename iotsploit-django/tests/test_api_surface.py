from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import django
import pytest
from django.test import Client


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

pytestmark = pytest.mark.contract

PRODUCTION_ENVIRONMENT = {
    "SECRET_KEY": "production-secret-key",
    "ALLOWED_HOSTS": "rig.example,127.0.0.1",
    "CORS_ALLOWED_ORIGINS": "https://rig.example,http://127.0.0.1",
}


@pytest.mark.parametrize(
    "path",
    [
        "/api/scan_all_devices/",
        "/api/scan_device/driver/",
        "/api/list_devices/",
        "/api/initialize_devices/",
        "/api/cleanup_devices/",
    ],
)
def test_device_actions_reject_get(path: str):
    assert Client().get(path).status_code == 405


def test_device_scan_reaches_the_view(monkeypatch):
    manager = Mock()
    manager.list_drivers.return_value = []
    monkeypatch.setattr(
        "iotsploit_django.view_handlers.device_views.get_device_driver_manager",
        lambda: manager,
    )

    response = Client(enforce_csrf_checks=True).post("/api/scan_all_devices/")

    assert response.status_code == 200
    assert response.json()["devices_found"] == 0


def test_remote_plugin_registration_route_is_absent():
    response = Client().post("/api/plugins/exploits/discovered/")

    assert response.status_code == 404


def _load_production_settings(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "from django.conf import Settings; "
            "settings = Settings('iotsploit_django.settings.prod'); "
            "print(json.dumps({"
            "'debug': settings.DEBUG, "
            "'hosts': settings.ALLOWED_HOSTS, "
            "'cors': settings.CORS_ALLOWED_ORIGINS, "
            "'cors_all': settings.CORS_ALLOW_ALL_ORIGINS"
            "}))"
        ),
    ]
    process_environment = os.environ.copy()
    for name in PRODUCTION_ENVIRONMENT:
        process_environment.pop(name, None)
    process_environment.update(environment)
    return subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=process_environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_production_settings_are_explicit_and_restrictive():
    result = _load_production_settings(PRODUCTION_ENVIRONMENT)

    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    assert loaded == {
        "debug": False,
        "hosts": ["rig.example", "127.0.0.1"],
        "cors": ["https://rig.example", "http://127.0.0.1"],
        "cors_all": False,
    }


@pytest.mark.parametrize("missing_name", PRODUCTION_ENVIRONMENT)
def test_production_settings_reject_missing_security_configuration(missing_name: str):
    environment = PRODUCTION_ENVIRONMENT.copy()
    environment.pop(missing_name)

    result = _load_production_settings(environment)

    assert result.returncode != 0
    assert missing_name in result.stderr
