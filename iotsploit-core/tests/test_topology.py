"""Plane T primitives: buses and typed edges.

Buses exist before any DBC import because CAN messages anchor to a bus, not to
a component. Without a real bus id, an importer has to invent string anchors
that every later row must be migrated off.
"""

from __future__ import annotations

import pytest

from iotsploit_core.domain.target import Bus, Component, Edge, GenericTarget, Interface, Vehicle

pytestmark = pytest.mark.unit


def target(cls=Vehicle, **kwargs):
    base = dict(
        target_id="t1",
        name="Zeekr",
        type="vehicle" if cls is Vehicle else "ecu",
        components=[
            Component(component_id="c_vgm", name="VGM", type="ecu"),
            Component(component_id="c_tcam", name="TCAM", type="ecu"),
        ],
        interfaces=[Interface(interface_id="i_eth0", name="eth0", type="ethernet")],
        buses=[Bus(bus_id="bus_can_b", name="CAN-B", type="can")],
    )
    base.update(kwargs)
    return cls(**base)


def test_a_target_without_topology_is_unchanged():
    """Every existing target is in this state."""
    plain = Vehicle(target_id="t1", name="T", type="vehicle")

    assert plain.buses == [] and plain.edges == []


def test_buses_and_edges_round_trip():
    original = target(edges=[Edge(source="c_vgm", target="bus_can_b", relation="bus_member")])
    reloaded = Vehicle(**original.model_dump())

    assert reloaded.buses[0].bus_id == "bus_can_b"
    assert reloaded.edges[0].relation == "bus_member"


@pytest.mark.parametrize(
    "source,dest",
    [
        ("c_vgm", "bus_can_b"),  # component on a bus
        ("c_vgm", "c_tcam"),  # component to component
        ("c_tcam", "i_eth0"),  # component to interface
        ("t1", "c_vgm"),  # the target itself is a valid endpoint
    ],
)
def test_edges_may_join_any_known_id(source, dest):
    result = target(edges=[Edge(source=source, target=dest, relation="connects")])

    assert result.edges[0].source == source


@pytest.mark.parametrize("bad", [{"source": "ghost", "target": "c_vgm"}, {"source": "c_vgm", "target": "ghost"}])
def test_an_edge_to_an_unknown_id_is_rejected(bad):
    """A dangling edge is a topology claim that reads as true and answers
    reachability questions wrongly. Rejecting the write beats storing a lie."""
    with pytest.raises(ValueError, match="unknown"):
        target(edges=[Edge(relation="connects", **bad)])


def test_the_error_names_the_offending_endpoint():
    with pytest.raises(ValueError) as excinfo:
        target(edges=[Edge(source="c_vgm", target="typo_bus", relation="bus_member")])

    assert "typo_bus" in str(excinfo.value) and "bus_member" in str(excinfo.value)


def test_removing_a_component_invalidates_its_edges():
    """Pins the consequence: an edit that orphans an edge fails loudly rather
    than leaving the graph quietly wrong."""
    stored = target(edges=[Edge(source="c_vgm", target="bus_can_b", relation="bus_member")]).model_dump()
    stored["components"] = [c for c in stored["components"] if c["component_id"] != "c_vgm"]

    with pytest.raises(ValueError, match="c_vgm"):
        Vehicle(**stored)


def test_parallel_edges_between_the_same_pair_are_allowed():
    """Different tools assert different relationships over the same pair."""
    result = target(
        edges=[
            Edge(source="c_vgm", target="c_tcam", relation="connects"),
            Edge(source="c_vgm", target="c_tcam", relation="reachable_from", properties={"via": "doip"}),
        ]
    )

    assert len(result.edges) == 2


def test_topology_works_on_generic_targets_too():
    result = target(cls=GenericTarget, edges=[Edge(source="c_vgm", target="bus_can_b", relation="bus_member")])

    assert result.edges[0].target == "bus_can_b"


def test_edge_properties_are_preserved():
    result = target(
        edges=[Edge(source="c_vgm", target="bus_can_b", relation="bus_member", properties={"baud": 500000})]
    )

    assert result.model_dump()["edges"][0]["properties"]["baud"] == 500000
