"""The shell's device commands are answered by the running backend.

The backend owns the drivers and the hardware, and the UI asks it over HTTP.
The shell asking the same routes is what keeps the two showing the same
devices; these tests pin the requests it sends and what it tells the operator
when the backend refuses or is not there.
"""

from __future__ import annotations

import pytest
import requests

from iotsploit_cli.commands import device_commands
from iotsploit_cli.commands.device_commands import DeviceCommands
from iotsploit_mcp.adapters.django_http_client import DjangoHttpError


pytestmark = pytest.mark.unit

DEVICES = {
    "status": "success",
    "devices": [
        {"device_id": "eth_vlan_enp42s0", "name": "Ethernet VLANs (enp42s0)", "driver": "drv_eth_vlan"},
        {"device_id": "vcan_001", "name": "SocketCAN_vcan0", "driver": "drv_socketcan"},
    ],
}


class Backend:
    """The routes the shell calls, answering as the Django views do."""

    def __init__(self, answers=None, down=False):
        self.answers = {"/api/list_devices/": DEVICES, **(answers or {})}
        self.down = down
        self.calls = []

    def client(self, *, base_url, timeout_s):
        return self

    def get(self, path, *, params=None):
        return self._answer("GET", path, None)

    def post(self, path, *, json=None):
        return self._answer("POST", path, json)

    def _answer(self, method, path, payload):
        if self.down:
            raise DjangoHttpError("Django API not reachable") from requests.ConnectionError()
        self.calls.append((method, path, payload))
        return self.answers[path]


class Shell(DeviceCommands):
    pass


@pytest.fixture
def said(monkeypatch):
    lines = []
    monkeypatch.setattr(device_commands.logger, "info", lambda message, *a: lines.append(str(message)))
    monkeypatch.setattr(device_commands.logger, "error", lambda message, *a: lines.append(str(message)))
    return lines


def _use(monkeypatch, backend):
    monkeypatch.setattr(device_commands, "DjangoHttpClient", backend.client)
    return backend


def test_run_sends_the_command_to_the_driver_that_owns_the_device(monkeypatch, said):
    backend = _use(monkeypatch, Backend({
        "/api/execute_device_command/drv_eth_vlan/": {"status": "success", "result": "Added VLAN enp42s0.67"},
    }))

    Shell().do_execute_device_command("eth_vlan_enp42s0 add_vlan vlan_id=67 address=172.31.67.6/16")

    assert backend.calls == [
        ("POST", "/api/list_devices/", None),
        (
            "POST",
            "/api/execute_device_command/drv_eth_vlan/",
            {
                "command": "add_vlan",
                "device_id": "eth_vlan_enp42s0",
                "args": {"vlan_id": 67, "address": "172.31.67.6/16"},
            },
        ),
    ]
    assert any("Added VLAN enp42s0.67" in line for line in said)


def test_the_drivers_refusal_reaches_the_operator_as_written(monkeypatch, said):
    _use(monkeypatch, Backend({
        "/api/execute_device_command/drv_eth_vlan/": {
            "status": "error",
            "message": "VLAN enp42s0.67 already exists",
        },
    }))

    Shell().do_execute_device_command("eth_vlan_enp42s0 add_vlan vlan_id=67")

    assert any("VLAN enp42s0.67 already exists" in line for line in said)


def test_an_unknown_device_sends_no_command(monkeypatch, said):
    backend = _use(monkeypatch, Backend())

    Shell().do_execute_device_command("can_001 send id=0x123")

    assert backend.calls == [("POST", "/api/list_devices/", None)]
    assert any("No device 'can_001'" in line for line in said)


@pytest.mark.parametrize("argument", ("", "eth_vlan_enp42s0", "eth_vlan_enp42s0 add_vlan vlan_id"))
def test_an_incomplete_command_line_never_reaches_the_backend(monkeypatch, said, argument):
    backend = _use(monkeypatch, Backend())

    Shell().do_execute_device_command(argument)

    assert backend.calls == []
    assert said


def test_a_stopped_backend_says_to_start_it(monkeypatch, said):
    _use(monkeypatch, Backend(down=True))

    Shell().do_list_devices("")

    assert any("Run runserver first" in line for line in said)


def test_the_device_list_is_the_backends(monkeypatch, said):
    backend = _use(monkeypatch, Backend())

    Shell().do_list_devices("")

    assert backend.calls == [("POST", "/api/list_devices/", None)]
    assert any("eth_vlan_enp42s0" in line and "drv_eth_vlan" in line for line in said)
