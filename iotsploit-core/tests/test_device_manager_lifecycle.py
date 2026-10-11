"""A device's recorded state follows what actually happened to it.

The transition table used to be overruled by an "only move up" fallback, close
never recorded anything, and a failed command was put back to connected before
the error was looked at. The result was a state that lied: a closed device
still read connected and could not be opened again, a device that was never
connected read connected after one command, and an unplugged adapter never
showed an error. Re-initializing wiped the states but left every probe leased,
so the second "initialize all" was refused by the manager's own lease.
"""

from __future__ import annotations

import pytest

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.core.device_manager import DeviceDriverManager
from iotsploit_core.core.device_spec import DeviceState
from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_core.ports.resource_lease import ResourceBusyError

pytestmark = pytest.mark.unit

DRIVER = "drv_adapter"
DEVICE = Device(device_id="adapter_1", name="Adapter 1", device_type=DeviceType.USB)


class MemoryLease:
    def __init__(self):
        self.held: dict[str, str] = {}

    def acquire(self, resource, owner):
        if resource in self.held:
            raise ResourceBusyError(resource, self.held[resource])
        self.held[resource] = owner

    def release(self, resource, owner):
        if self.held.get(resource) == owner:
            del self.held[resource]


class AdapterDriver(BaseDeviceDriver):
    """One leased adapter; the `unplug` command fails the way a pulled cable does."""

    def resource_key(self, device):
        return "usb:1366-1/debug"

    def _scan_impl(self):
        return [DEVICE]

    def _initialize_impl(self, device):
        return True

    def _connect_impl(self, device):
        return True

    def _command_impl(self, device, command, args=None):
        if command == "unplug":
            raise OSError("device disconnected")
        return "ok"

    def _close_impl(self, device):
        return True


class Repo:
    def get_enabled(self, driver_name):
        return None

    def set_enabled(self, driver_name, enabled, description=None):
        pass

    def list_enabled(self):
        return {}


@pytest.fixture
def lease():
    return MemoryLease()


@pytest.fixture
def manager(monkeypatch, tmp_path, lease):
    monkeypatch.setattr(DeviceDriverManager, "_instance", None)
    monkeypatch.setattr(DeviceDriverManager, "load_plugins", lambda self: None)
    manager = DeviceDriverManager(driver_state_repo=Repo(), plugins_dir=tmp_path,
                                  usb_config_file=tmp_path / "none.json", resource_lease=lease)
    manager.drivers[DRIVER] = AdapterDriver()
    manager.driver_requirements[DRIVER] = ()
    return manager


def state(manager):
    return manager.get_device_state(DRIVER, DEVICE.device_id)


def open_device(manager):
    manager.scan_devices(DRIVER)
    manager.initialize_device(DRIVER, DEVICE)
    manager.connect_device(DRIVER, DEVICE)


def test_a_closed_device_reads_disconnected_and_opens_again(manager, lease):
    open_device(manager)

    manager.close_device(DRIVER, DEVICE)

    assert state(manager) is DeviceState.DISCONNECTED
    assert lease.held == {}
    assert manager.connect_device(DRIVER, DEVICE)["status"] == "success"
    assert state(manager) is DeviceState.CONNECTED


def test_an_io_failure_on_a_connected_device_is_recorded_and_close_recovers(manager):
    open_device(manager)

    result = manager.execute_command(DRIVER, "unplug", DEVICE.device_id)

    assert result == {"status": "error", "message": "device disconnected"}
    assert state(manager) is DeviceState.ERROR
    manager.close_device(DRIVER, DEVICE)
    assert state(manager) is DeviceState.DISCONNECTED


def test_a_command_on_a_scanned_device_runs_without_claiming_it_connected(manager):
    """The UI commands straight after a scan; the device was never connected."""
    manager.scan_devices(DRIVER)

    result = manager.execute_command(DRIVER, "identify", DEVICE.device_id)

    assert result == {"status": "success", "result": "ok"}
    assert state(manager) is DeviceState.DISCOVERED


def test_a_rescan_does_not_demote_an_open_device(manager):
    open_device(manager)

    manager.scan_devices(DRIVER)

    assert state(manager) is DeviceState.CONNECTED


def test_initialize_all_can_run_twice_on_a_leased_device(manager, lease):
    first = manager.initialize_all_devices()[DRIVER]["devices"]
    second = manager.initialize_all_devices()[DRIVER]["devices"]

    assert [d["status"] for d in first + second] == ["success", "success"]
    assert state(manager) is DeviceState.CONNECTED
    assert lease.held == {"usb:1366-1/debug": f"device manager ({DRIVER})"}


def test_a_refused_transition_leaves_the_state_unchanged(manager):
    manager.scan_devices(DRIVER)

    manager._update_device_state(f"{DRIVER}::{DEVICE.device_id}", DeviceState.CONNECTED)

    assert state(manager) is DeviceState.DISCOVERED
