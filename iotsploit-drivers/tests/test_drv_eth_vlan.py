"""Ethernet VLAN CRUD is bounded to NetworkManager profiles owned by IoTSploit."""

from __future__ import annotations

import json
from importlib.metadata import entry_points
from types import SimpleNamespace

import pytest

from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_drivers.ethernet import drv_eth_vlan
from iotsploit_drivers.ethernet.drv_eth_vlan import EthernetVlanDriver


pytestmark = pytest.mark.unit


@pytest.fixture
def device() -> Device:
    return Device(
        device_id="eth_vlan_eth0",
        name="Ethernet VLANs (eth0)",
        device_type=DeviceType.Ethernet,
        attributes={"interface": "eth0"},
    )


@pytest.fixture
def driver() -> EthernetVlanDriver:
    return EthernetVlanDriver()


def config(vlan_id: int = 67) -> dict:
    return {
        "vlan_id": vlan_id,
        "address": "172.31.67.6/16",
        "local_mac": "02:80:5e:1f:00:06",
        "peer_ip": "172.31.67.5",
        "peer_mac": "02:80:5e:1f:00:05",
    }


def owned(vlan_id: int = 67) -> dict:
    return {
        "parent": "eth0",
        "vlan_id": vlan_id,
        "profile": f"iotsploit-vlan-eth0-{vlan_id}",
        "managed": True,
    }


def test_driver_entry_point_is_registered():
    available = {entry.name: entry for entry in entry_points(group="iotsploit.device_drivers")}

    assert available["drv_eth_vlan"].load() is EthernetVlanDriver


def test_scan_returns_physical_parent_with_its_vlan_profiles(driver, monkeypatch):
    monkeypatch.setattr(
        drv_eth_vlan,
        "_ethernet_devices",
        lambda: [{"interface": "eth0", "type": "ethernet", "state": "connected", "connection": "wired"}],
    )
    monkeypatch.setattr(drv_eth_vlan, "_vlan_profiles", lambda: [owned(67), {**owned(17), "parent": "eth1"}])

    scanned = driver._scan_impl()

    assert [item.device_id for item in scanned] == ["eth_vlan_eth0"]
    assert scanned[0].device_type is DeviceType.Ethernet
    assert [item["vlan_id"] for item in scanned[0].attributes["vlans"]] == [67]


def test_scan_skips_parents_networkmanager_does_not_manage(monkeypatch):
    """Containers and hypervisors present their endpoints as ethernet too.

    On a developer box with Docker running, 24 of 25 ethernet rows are veth
    or vmnet endpoints. NetworkManager leaves them unmanaged and will not
    activate a VLAN built on one, so offering them as parents only invites a
    failure the operator cannot act on.
    """
    monkeypatch.setattr(
        drv_eth_vlan,
        "_run",
        lambda argv: (
            "enp42s0:ethernet:connected:wired\n"
            "veth47dce99:ethernet:unmanaged:\n"
            "vmnet8:ethernet:unmanaged:\n"
            "wlp0s20f3:wifi:connected:home\n"
        ),
    )

    assert [row["interface"] for row in drv_eth_vlan._ethernet_devices()] == ["enp42s0"]


def test_add_calls_only_the_bounded_add_verb(driver, device, monkeypatch):
    calls = []
    monkeypatch.setattr(drv_eth_vlan, "_vlan_profiles", lambda: [])
    monkeypatch.setattr(drv_eth_vlan, "_interface_addresses", lambda interface: set())
    monkeypatch.setattr(
        drv_eth_vlan,
        "privileged_call",
        lambda verb, args: calls.append((verb, args)) or SimpleNamespace(ok=True, stdout="", stderr="", exit=0),
    )

    result = driver._command_impl(device, "add_vlan", config())

    assert result == "Added VLAN eth0.67"
    assert calls == [("vlan-add", {"parent": "eth0", **config()})]


def test_add_refuses_an_address_already_on_the_parent(driver, device, monkeypatch):
    monkeypatch.setattr(drv_eth_vlan, "_vlan_profiles", lambda: [])
    monkeypatch.setattr(drv_eth_vlan, "_interface_addresses", lambda interface: {"172.31.67.6"})

    with pytest.raises(ValueError, match="already assigned to parent eth0"):
        driver._command_impl(device, "add_vlan", config())


def test_edit_refuses_a_profile_not_owned_by_iotsploit(driver, device, monkeypatch):
    monkeypatch.setattr(
        drv_eth_vlan,
        "_vlan_profiles",
        lambda: [{**owned(), "profile": "operator-vlan", "managed": False}],
    )

    with pytest.raises(ValueError, match="not managed by IoTSploit"):
        driver._command_impl(device, "edit_vlan", config())


def test_delete_calls_only_the_bounded_delete_verb(driver, device, monkeypatch):
    calls = []
    monkeypatch.setattr(drv_eth_vlan, "_vlan_profiles", lambda: [owned()])
    monkeypatch.setattr(
        drv_eth_vlan,
        "privileged_call",
        lambda verb, args: calls.append((verb, args)) or SimpleNamespace(ok=True, stdout="", stderr="", exit=0),
    )

    result = driver._command_impl(device, "delete_vlan", {"vlan_id": 67})

    assert result == "Deleted VLAN eth0.67"
    assert calls == [("vlan-delete", {"parent": "eth0", "vlan_id": 67})]


def test_status_reports_profiles_without_a_privileged_call(driver, device, monkeypatch):
    monkeypatch.setattr(drv_eth_vlan, "_vlan_profiles", lambda: [owned()])
    monkeypatch.setattr(
        drv_eth_vlan,
        "privileged_call",
        lambda *args: pytest.fail("status must be read-only"),
    )

    result = json.loads(driver._command_impl(device, "vlan_status"))

    assert result == {"parent": "eth0", "vlans": [owned()]}


@pytest.mark.parametrize(
    "values",
    [
        {**config(), "vlan_id": True},
        {**config(), "address": "172.31.67.6"},
        {**config(), "local_mac": "01:80:5e:1f:00:06"},
        {**config(), "peer_mac": None},
    ],
)
def test_invalid_vlan_configuration_never_reaches_privileged_helper(driver, device, monkeypatch, values):
    monkeypatch.setattr(
        drv_eth_vlan,
        "privileged_call",
        lambda *args: pytest.fail("invalid input must not reach the helper"),
    )

    with pytest.raises(ValueError):
        driver._command_impl(device, "add_vlan", values)
