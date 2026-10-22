"""A command whose parameter offers what is plugged in right now."""

from __future__ import annotations

from importlib.metadata import entry_points
from types import SimpleNamespace

import pytest

from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_drivers.usb_explorer import drv_usb_explorer
from iotsploit_drivers.usb_explorer.drv_usb_explorer import UsbExplorerDriver


pytestmark = pytest.mark.unit


def fake(bus: int, address: int, vendor: int, product: int, klass: int = 0x09) -> SimpleNamespace:
    return SimpleNamespace(
        bus=bus,
        address=address,
        idVendor=vendor,
        idProduct=product,
        bDeviceClass=klass,
        bcdUSB=0x0210,
        bNumConfigurations=1,
        iManufacturer=1,
        iProduct=2,
        iSerialNumber=3,
    )


STRINGS = {1: "SEGGER", 2: "J-Link", 3: "000441005981"}


@pytest.fixture
def driver(monkeypatch) -> UsbExplorerDriver:
    devices = [fake(1, 49, 0x1366, 0x0101, klass=0x00), fake(1, 1, 0x1D6B, 0x0002)]
    monkeypatch.setattr(drv_usb_explorer.usb.core, "find", lambda find_all: iter(devices))
    monkeypatch.setattr(
        drv_usb_explorer.usb.util,
        "get_string",
        lambda device, index: STRINGS[index] if device.idVendor == 0x1366 else None,
    )
    return UsbExplorerDriver()


@pytest.fixture
def host() -> Device:
    return Device(
        device_id="usb_explorer_host",
        name="USB Explorer (this host)",
        device_type=DeviceType.USB,
    )


def test_driver_entry_point_is_registered():
    available = {entry.name: entry for entry in entry_points(group="iotsploit.device_drivers")}

    assert available["drv_usb_explorer"].load() is UsbExplorerDriver


def test_parameters_offer_the_devices_present_now(driver):
    options = driver.get_command_parameters()["describe"]["usb_device"]["options"]

    assert options == [
        {"value": "001:001", "label": "hub [1d6b:0002] at 001:001"},
        {"value": "001:049", "label": "SEGGER J-Link [1366:0101] at 001:049"},
    ]


def test_the_scan_is_not_written_into_the_declaration(driver):
    driver.get_command_parameters()

    declared = driver.supported_commands["describe"]["parameters"]["usb_device"]
    assert declared["options"] == []


def test_describe_acts_on_the_chosen_address(driver, host):
    result = driver._command_impl(host, "describe", {"usb_device": "001:049"})

    assert "Address:      001:049" in result
    assert "0x1366 SEGGER" in result
    assert "Serial:       000441005981" in result


def test_a_device_that_has_been_unplugged_says_so(driver, host):
    with pytest.raises(ValueError, match="No USB device at 001:050"):
        driver._command_impl(host, "describe", {"usb_device": "001:050"})
