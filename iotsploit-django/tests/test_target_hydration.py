"""Target hydration from dict payloads.

`create_target_instance` and `parse_and_set_target_from_json` share the field
hydration but deliberately choose the target class differently. That difference
is the thing most easily lost when the two are merged, so it is pinned here.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_core.domain.target import ADBDevice, GenericTarget, Vehicle  # noqa: E402

pytestmark = pytest.mark.unit

PAYLOAD = {
    "target_id": "t1",
    "name": "Zeekr 001",
    "type": "vehicle",
    "properties": {"vin": "LB37622Z0PX000001"},
    "ip_address": "198.18.34.1",
    "location": "lab-3",
    "components": [
        {"component_id": "c_dhu", "name": "DHU", "type": "adb_device", "adb_serial_id": "ABC123", "odd": "kept"}
    ],
    "interfaces": [{"interface_id": "i1", "name": "eth0", "type": "ethernet"}],
}


@pytest.fixture
def hydrate():
    from iotsploit_django.adapters.django.target_models import TargetManager

    return TargetManager._hydrate_target


def test_dict_components_become_typed_components(hydrate):
    target = hydrate(PAYLOAD, Vehicle)

    assert isinstance(target.components[0], ADBDevice)
    assert target.components[0].adb_serial_id == "ABC123"
    assert target.components[0].properties["odd"] == "kept"


def test_already_typed_components_pass_through(hydrate):
    """get_all_targets returns dicts, but callers also hand over models."""
    comp = ADBDevice(component_id="c1", name="DHU", type="adb_device", adb_serial_id="X")
    target = hydrate({**PAYLOAD, "components": [comp]}, Vehicle)

    assert target.components[0] is comp


def test_scalar_fields_round_trip(hydrate):
    target = hydrate(PAYLOAD, Vehicle)

    assert (target.target_id, target.name, target.type) == ("t1", "Zeekr 001", "vehicle")
    assert target.ip_address == "198.18.34.1" and target.location == "lab-3"
    assert target.properties["vin"] == "LB37622Z0PX000001"
    assert target.status == "active"


def test_missing_collections_default_to_empty(hydrate):
    target = hydrate({"target_id": "t1", "name": "T", "type": "vehicle"}, Vehicle)

    assert target.components == [] and target.interfaces == []
    assert target.properties == {}


def test_null_collections_do_not_crash(hydrate):
    """A stored row can hold JSON null for components; None is not a list."""
    payload = {"target_id": "t1", "name": "T", "type": "vehicle", "components": None, "properties": None}
    target = hydrate(payload, Vehicle)

    assert target.components == [] and target.properties == {}


def test_the_caller_chooses_the_class(hydrate):
    """Hydration is shared; class selection is not. The request path knows only
    Vehicle and GenericTarget, the JSON import path honours registered types."""
    assert isinstance(hydrate(PAYLOAD, Vehicle), Vehicle)
    assert isinstance(hydrate({**PAYLOAD, "type": "ecu"}, GenericTarget), GenericTarget)


def test_topology_hydrates_from_stored_dicts(hydrate):
    """buses/edges arrive as plain dicts from the JSON columns."""
    payload = {
        **PAYLOAD,
        "components": [{"component_id": "c_vgm", "name": "VGM", "type": "ecu"}],
        "buses": [{"bus_id": "bus_can_b", "name": "CAN-B", "type": "can"}],
        "edges": [{"source": "c_vgm", "target": "bus_can_b", "relation": "bus_member"}],
    }
    target = hydrate(payload, Vehicle)

    assert target.buses[0].name == "CAN-B"
    assert target.edges[0].relation == "bus_member"


def test_targets_without_topology_hydrate_to_empty(hydrate):
    target = hydrate(PAYLOAD, Vehicle)

    assert target.buses == [] and target.edges == []


def test_facets_hydrate_from_stored_dicts(hydrate):
    payload = {
        **PAYLOAD,
        "components": [
            {"component_id": "c_tcam", "name": "TCAM", "type": "ecu", "facets": {"doip": {"logical_address": 4113}}}
        ],
    }
    target = hydrate(payload, Vehicle)

    assert target.components[0].facet("doip").logical_address == 4113
