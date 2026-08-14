"""Folding the old ``interfaces`` list into ``components``.

There is no migration script: stored targets are folded every time they are
read and written back folded on the next save. That only works if folding is
idempotent and leaves every edge pointing where it pointed before.
"""

from __future__ import annotations

import pytest

from iotsploit_core.domain.target import (
    Bus,
    Component,
    Edge,
    Vehicle,
    fold_legacy_interfaces,
)

pytestmark = pytest.mark.unit


def stored(**overrides):
    data = {
        "target_id": "zeekr_did_demo",
        "name": "Zeekr 001",
        "type": "vehicle",
        "components": [
            {"component_id": "c_tcam", "name": "TCAM", "type": "ecu"},
        ],
        "interfaces": [
            {"interface_id": "i_eth0", "name": "eth0", "type": "ethernet"},
        ],
    }
    data.update(overrides)
    return data


def test_an_interface_becomes_a_component_keeping_its_id():
    """The id is the whole reason edges survive; it must not be regenerated."""
    folded = fold_legacy_interfaces(stored())

    ids = [c["component_id"] for c in folded["components"]]
    assert ids == ["c_tcam", "i_eth0"]


def test_the_kind_is_carried_over_as_the_type():
    folded = fold_legacy_interfaces(stored())
    eth0 = folded["components"][1]

    assert eth0["type"] == "ethernet"
    assert eth0["name"] == "eth0"
    assert "interface_id" not in eth0, "the old key would land in properties"


def test_the_legacy_key_is_gone_afterwards():
    assert "interfaces" not in fold_legacy_interfaces(stored())


def test_an_empty_legacy_list_still_drops_the_key():
    """Otherwise half the targets keep an empty list forever."""
    assert "interfaces" not in fold_legacy_interfaces(stored(interfaces=[]))


def test_folding_twice_changes_nothing():
    """Every read folds; a second pass must not duplicate the row."""
    once = fold_legacy_interfaces(stored())
    twice = fold_legacy_interfaces(once)

    assert twice == once


def test_an_id_already_taken_is_not_added_again():
    data = stored(
        components=[{"component_id": "i_eth0", "name": "eth0", "type": "ethernet"}]
    )

    folded = fold_legacy_interfaces(data)

    assert len(folded["components"]) == 1


def test_the_stored_dict_is_not_modified():
    """Callers pass rows straight out of the database."""
    data = stored()

    fold_legacy_interfaces(data)

    assert data["interfaces"] == [
        {"interface_id": "i_eth0", "name": "eth0", "type": "ethernet"}
    ]
    assert len(data["components"]) == 1


def test_an_interface_without_a_type_still_lands_somewhere_sensible():
    data = stored(interfaces=[{"interface_id": "i_x", "name": "x"}])

    folded = fold_legacy_interfaces(data)

    assert folded["components"][1]["type"] == "interface"


def test_a_target_with_no_legacy_key_is_returned_untouched():
    data = {"target_id": "t1", "name": "T", "type": "vehicle", "components": []}

    assert fold_legacy_interfaces(data) is data


def test_an_edge_onto_a_folded_interface_still_validates():
    """The point of the whole exercise: topology does not need rewriting."""
    folded = fold_legacy_interfaces(
        stored(
            buses=[{"bus_id": "bus_can_b", "name": "CAN-B", "type": "can"}],
            edges=[{"source": "c_tcam", "target": "i_eth0", "relation": "hosts"}],
        )
    )

    target = Vehicle(
        target_id=folded["target_id"],
        name=folded["name"],
        type="vehicle",
        components=[Component(**c) for c in folded["components"]],
        buses=[Bus(**b) for b in folded["buses"]],
        edges=[Edge(**e) for e in folded["edges"]],
    )

    assert target.edges[0].target == "i_eth0"


def test_an_edge_onto_an_id_that_was_never_folded_still_fails():
    """The fold must not become a way to smuggle in an unknown endpoint."""
    with pytest.raises(ValueError, match="unknown target"):
        Vehicle(
            target_id="t1",
            name="T",
            type="vehicle",
            components=[Component(component_id="c_tcam", name="TCAM", type="ecu")],
            edges=[Edge(source="c_tcam", target="i_gone", relation="hosts")],
        )
