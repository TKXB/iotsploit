"""A device command must reach the driver, and the device, it was addressed to.

`POST /api/execute_device_command/<driver>/` is the only route between a
button in the UI and a driver's `_command_impl`, and until now nothing tested
it. The rules below are the ones the PCAN driver broke, each in a way that
looked like success from the outside:

* **A command arrives without an initialize.** The UI scans and then commands;
  it never calls `/api/initialize_devices/` in between. A driver that keeps
  the thing it needs -- an interface name, a handle -- in state that only
  `initialize` sets therefore acts on `None`.
* **The addressed device is the one the driver receives.** The manager
  resolves `device_id` out of the driver's own scan results. A driver that
  reads a single "current device" attribute instead will happily configure the
  wrong bus and report success, which is worse than failing.
* **An unknown `device_id` is a structured error.** The UI reads
  `data['result']` on a 200 and shows the raw body otherwise, so a stack trace
  behind a 500 reaches an operator as noise.

The manager is real here; only the driver is a stub. Testing this against a
mocked manager would assert nothing about the lifecycle, which is where the
defect was.
"""

from __future__ import annotations

import json
import os

import django
import pytest
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_core.core.base_plugin import BaseDeviceDriver  # noqa: E402
from iotsploit_core.core.device_manager import DeviceDriverManager  # noqa: E402
from iotsploit_core.domain.device import Device, DeviceType  # noqa: E402

pytestmark = pytest.mark.contract

DRIVER = "drv_stub"
SCAN_PATH = f"/api/scan_device/{DRIVER}/"
COMMAND_PATH = f"/api/execute_device_command/{DRIVER}/"


def _device(device_id: str) -> Device:
    return Device(device_id=device_id, name=f"stub {device_id}", device_type=DeviceType.CAN)


class RecordingDriver(BaseDeviceDriver):
    """Two devices, and a log of every lifecycle call the manager makes.

    Two and not one on purpose: with a single device, a driver that ignores
    the device it was handed passes anyway.
    """

    def __init__(self):
        super().__init__()
        self.supported_commands = {"identify": "Report which device answered"}
        self.calls: list[tuple] = []

    def _scan_impl(self) -> list[Device]:
        self.calls.append(("scan",))
        return [_device("stub_001"), _device("stub_002")]

    def _initialize_impl(self, device: Device) -> bool:
        self.calls.append(("initialize", device.device_id))
        return True

    def _connect_impl(self, device: Device) -> bool:
        self.calls.append(("connect", device.device_id))
        return True

    def _command_impl(self, device: Device, command: str, args=None):
        self.calls.append(("command", device.device_id, command))
        return f"{command} on {device.device_id}"


class ForgetfulRepo:
    """The driver-state port, backed by nothing: this test persists no state."""

    def get_enabled(self, driver_name: str):
        return None

    def set_enabled(self, driver_name: str, enabled: bool, description: str | None = None) -> None:
        pass

    def list_enabled(self) -> dict[str, bool]:
        return {}


@pytest.fixture
def driver(monkeypatch, tmp_path) -> RecordingDriver:
    """A real manager carrying one stub driver, wired into both view modules.

    `DeviceDriverManager` is a singleton, so the instance is swapped rather
    than constructed alongside the process-wide one; monkeypatch restores it.
    `load_plugins` is silenced because the real entry points would drag every
    installed driver into a test about the manager.
    """
    monkeypatch.setattr(DeviceDriverManager, "_instance", None)
    monkeypatch.setattr(DeviceDriverManager, "load_plugins", lambda self: None)

    manager = DeviceDriverManager(
        driver_state_repo=ForgetfulRepo(),
        plugins_dir=tmp_path,
        usb_config_file=tmp_path / "no_usb_config.json",
    )
    stub = RecordingDriver()
    manager.drivers[DRIVER] = stub
    manager.driver_requirements[DRIVER] = ()

    for module in (
        "iotsploit_django.view_handlers.device_views",
        "iotsploit_django.view_handlers.plugin_views",
    ):
        monkeypatch.setattr(f"{module}.get_device_driver_manager", lambda: manager)

    return stub


def _command(device_id: str, command: str = "identify"):
    return Client().post(
        COMMAND_PATH,
        data=json.dumps({"command": command, "device_id": device_id}),
        content_type="application/json",
    )


def test_a_command_reaches_the_driver_without_an_initialize(driver):
    """The UI scans and commands. Nothing in between calls initialize."""
    assert Client().post(SCAN_PATH).status_code == 200

    response = _command("stub_001")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "result": "identify on stub_001"}
    assert driver.calls == [("scan",), ("command", "stub_001", "identify")]


def test_the_driver_receives_the_device_the_request_named(driver):
    """Two adapters, and the second one is the one that must answer."""
    Client().post(SCAN_PATH)

    assert _command("stub_002").json()["result"] == "identify on stub_002"
    assert ("command", "stub_002", "identify") in driver.calls
    assert not any(call[:2] == ("command", "stub_001") for call in driver.calls)


def test_an_unknown_device_is_an_error_an_operator_can_read(driver):
    Client().post(SCAN_PATH)

    response = _command("stub_404")

    # 200 with status error, not a 500: the UI shows the body verbatim.
    assert response.status_code == 200
    assert response.json() == {"status": "error", "message": "Device stub_404 not found"}
    assert not any(call[0] == "command" for call in driver.calls)


def test_a_command_before_any_scan_does_not_reach_the_driver(driver):
    """The driver's devices come from its own scan, so there is nothing to address yet."""
    response = _command("stub_001")

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert driver.calls == []


def test_the_command_route_refuses_get(driver):
    """The client contract that broke in the first place, on the route it broke on."""
    assert Client().get(COMMAND_PATH).status_code == 405


def test_a_command_naming_no_driver_does_not_reach_a_different_one(driver):
    response = Client().post(
        "/api/execute_device_command/drv_absent/",
        data=json.dumps({"command": "identify", "device_id": "stub_001"}),
        content_type="application/json",
    )

    assert response.json() == {"status": "error", "message": "Driver drv_absent is disabled"}
    assert driver.calls == []
