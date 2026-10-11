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
    """A bare command mixin that records what it would print to the shell."""

    _lines: list[str] = []

    def poutput(self, message="", *, end="\n"):
        Shell._lines.append(str(message))

    def perror(self, message="", *, end="\n", apply_style=True):
        Shell._lines.append(str(message))


class Confirm:
    """Input_Mgr's yes/no prompt, answered in advance."""

    def __init__(self, answer):
        self.answer = answer

    def yes_no_input(self, _question, default=False):
        return self.answer


@pytest.fixture
def said():
    Shell._lines = []
    return Shell._lines


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


def test_a_json_value_is_sent_as_json(monkeypatch, said):
    backend = _use(monkeypatch, Backend({
        "/api/execute_device_command/drv_eth_vlan/": {"status": "success", "result": "ok"},
    }))

    Shell().do_execute_device_command("""eth_vlan_enp42s0 flash 'options={"target": "sram"}' verify=true""")

    assert backend.calls[-1][2]["args"] == {"options": {"target": "sram"}, "verify": True}


def test_initialize_asks_the_backend_to_reopen_every_device(monkeypatch, said):
    backend = _use(monkeypatch, Backend({
        "/api/initialize_devices/": {
            "status": "success",
            "results": {
                "drv_iotsploit_fpga": {
                    "status": "success",
                    "devices": [{"device": "Lattice ECP5", "status": "success", "message": "Successfully connected"}],
                },
                "drv_esp32": {"status": "error", "message": "Failed to scan: port busy"},
            },
        },
    }))
    monkeypatch.setattr(device_commands.Input_Mgr, "Instance", lambda: Confirm(True))

    Shell().do_initialize_devices("")

    assert backend.calls == [("POST", "/api/initialize_devices/", None)]
    assert any("Lattice ECP5" in line and "Successfully connected" in line for line in said)
    assert any("drv_esp32" in line and "port busy" in line for line in said)


def test_initialize_does_nothing_unless_confirmed(monkeypatch, said):
    backend = _use(monkeypatch, Backend())
    monkeypatch.setattr(device_commands.Input_Mgr, "Instance", lambda: Confirm(False))

    Shell().do_initialize_devices("")

    assert backend.calls == []


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


def test_driver_list_shows_state_and_availability_in_one_table(monkeypatch, said):
    _use(monkeypatch, Backend({
        "/api/list_device_drivers/": {
            "status": "success",
            "driver_info": [
                {"name": "drv_eth_vlan", "availability": {"available": False, "reason": "'nmcli' not on PATH"}},
                {"name": "drv_ft2232", "availability": {"available": True}},
            ],
        },
        "/api/get_driver_states/": {
            "status": "success",
            "drivers": {"drv_eth_vlan": {"enabled": True}, "drv_ft2232": {"enabled": False}},
        },
    }))

    Shell().do_list_device_drivers("")

    table = "\n".join(said)
    assert "drv_eth_vlan" in table and "'nmcli' not on PATH" in table
    assert "disabled" in table  # drv_ft2232
    assert "2 drivers · 1 enabled" in said


def test_the_device_list_is_the_backends(monkeypatch, said):
    backend = _use(monkeypatch, Backend())

    Shell().do_list_devices("")

    assert backend.calls == [("POST", "/api/list_devices/", None)]
    assert any("eth_vlan_enp42s0" in line and "drv_eth_vlan" in line for line in said)
