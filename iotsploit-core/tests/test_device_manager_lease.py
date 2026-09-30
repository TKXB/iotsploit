"""The device manager holds a device's resource lease for as long as it is initialized.

Without it, the Devices page could open a J-Link that a campaign's core monitor
is sampling, and both would read garbage from one probe.
"""

from __future__ import annotations

import pytest

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.core.device_manager import DeviceDriverManager
from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_core.ports.resource_lease import ResourceBusyError

pytestmark = pytest.mark.unit

DRIVER = "drv_probe"
RESOURCE = "usb:1366-1/debug"


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


class ProbeDriver(BaseDeviceDriver):
    def __init__(self, fail=False):
        super().__init__()
        self.fail = fail

    def resource_key(self, device):
        return RESOURCE

    def _initialize_impl(self, device):
        if self.fail:
            raise RuntimeError("cannot open probe")
        return True

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


def make_manager(monkeypatch, tmp_path, lease, driver):
    monkeypatch.setattr(DeviceDriverManager, "_instance", None)
    monkeypatch.setattr(DeviceDriverManager, "load_plugins", lambda self: None)
    manager = DeviceDriverManager(driver_state_repo=Repo(), plugins_dir=tmp_path,
                                  usb_config_file=tmp_path / "none.json", resource_lease=lease)
    manager.drivers[DRIVER] = driver
    manager.driver_requirements[DRIVER] = ()
    return manager


DEVICE = Device(device_id="jlink_1", name="J-Link 1", device_type=DeviceType.USB)


def test_initialized_device_holds_its_lease_until_closed(monkeypatch, tmp_path, lease):
    manager = make_manager(monkeypatch, tmp_path, lease, ProbeDriver())

    assert manager.initialize_device(DRIVER, DEVICE)["status"] == "success"
    assert lease.held == {RESOURCE: f"device manager ({DRIVER})"}
    manager.close_device(DRIVER, DEVICE)
    assert lease.held == {}


def test_a_device_a_monitor_holds_is_refused_with_the_holder(monkeypatch, tmp_path, lease):
    manager = make_manager(monkeypatch, tmp_path, lease, ProbeDriver())
    lease.acquire(RESOURCE, "campaign 7")

    result = manager.initialize_device(DRIVER, DEVICE)

    assert result["status"] == "error"
    assert "campaign 7" in result["message"]
    manager.close_device(DRIVER, DEVICE)  # closing must not steal the monitor's lease
    assert lease.held == {RESOURCE: "campaign 7"}


def test_failed_initialize_gives_the_lease_back(monkeypatch, tmp_path, lease):
    manager = make_manager(monkeypatch, tmp_path, lease, ProbeDriver(fail=True))

    assert manager.initialize_device(DRIVER, DEVICE)["status"] == "error"
    assert lease.held == {}


def test_driver_classes_and_capabilities_need_no_new_instance(monkeypatch, tmp_path, lease):
    manager = make_manager(monkeypatch, tmp_path, lease, ProbeDriver())

    assert manager.get_driver_class(DRIVER) is ProbeDriver
    assert manager.driver_classes() == {DRIVER: ProbeDriver}
    assert manager.get_driver_states()[DRIVER]["capabilities"] == []
