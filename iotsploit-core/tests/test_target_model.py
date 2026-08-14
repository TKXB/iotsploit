"""Target serialization.

These pin the behaviour the get_info() overrides used to provide by hand. The
one that matters is polymorphic serialization: pydantic serializes a
List[Component] against the *declared* type, so without SerializeAsAny every
subclass field is dropped silently -- no error, just missing data.
"""

from __future__ import annotations

import pytest

from iotsploit_core.domain.target import (
    ADBDevice,
    Component,
    ComponentFactory,
    ECUComponent,
    GenericTarget,
    NetworkComponent,
    Vehicle,
)

pytestmark = pytest.mark.unit


def build(cls=Vehicle):
    return cls(
        target_id="t1",
        name="Zeekr 001",
        type="vehicle" if cls is Vehicle else "ecu",
        properties={"vin": "LB37622Z0PX000001"},
        ip_address="198.18.34.1",
        location="lab-3",
        components=[
            ADBDevice(component_id="c_dhu", name="DHU", type="adb_device", adb_serial_id="ABC123"),
            NetworkComponent(component_id="c_tcam", name="TCAM", type="network", ip_address="198.18.34.1"),
            ECUComponent(component_id="c_vgm", name="VGM", type="ecu", address="0x1011"),
            Component(component_id="i1", name="eth0", type="ethernet"),
        ],
    )


@pytest.mark.parametrize("cls", [Vehicle, GenericTarget])
def test_subclass_component_fields_survive_serialization(cls):
    """Without SerializeAsAny this drops adb_serial_id and reports no error."""
    dumped = build(cls).model_dump()["components"]

    assert dumped[0]["adb_serial_id"] == "ABC123"
    assert dumped[1]["ip_address"] == "198.18.34.1"
    assert dumped[2]["address"] == "0x1011"


@pytest.mark.parametrize("cls", [Vehicle, GenericTarget])
def test_get_info_is_the_full_dump(cls):
    target = build(cls)
    info = target.get_info()

    assert info == target.model_dump()
    assert {"target_id", "name", "type", "status", "properties", "ip_address", "location"} <= set(info)
    assert len(info["components"]) == 4
    assert "interfaces" not in info, "one list of endpoints, not two"


def test_component_get_info_keeps_its_own_fields():
    comp = ADBDevice(component_id="c1", name="DHU", type="adb_device", adb_serial_id="ABC123")

    assert comp.get_info()["adb_serial_id"] == "ABC123"


def test_get_ecu_ip_reads_properties_then_the_typed_field():
    """Two storage locations for one attribute -- the reason facets exist."""
    target = Vehicle(
        target_id="t1",
        name="T",
        type="vehicle",
        components=[
            Component(component_id="c1", name="DHU", type="generic", properties={"ip_address": "198.18.36.1"}),
            NetworkComponent(component_id="c2", name="TCAM", type="network", ip_address="198.18.34.1"),
            Component(component_id="c3", name="VGM", type="generic"),
        ],
    )

    assert target.get_ecu_ip("dhu") == "198.18.36.1"
    assert target.get_ecu_ip("TCAM") == "198.18.34.1"
    assert target.get_ecu_ip("vgm") is None
    assert target.get_ecu_ip("absent") is None


def test_unknown_component_keys_are_kept_in_properties():
    comp = ComponentFactory.create_component(
        {"component_id": "c1", "name": "X", "type": "adb_device", "adb_serial_id": "S", "odd_key": "kept"}
    )

    assert comp.adb_serial_id == "S"
    assert comp.properties["odd_key"] == "kept"


def test_export_for_adb_includes_subclass_detail():
    exported = build().export_for_adb()

    assert exported["adb_devices"]["DHU"]["adb_serial_id"] == "ABC123"
