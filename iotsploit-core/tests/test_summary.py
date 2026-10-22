"""Projecting a target down to a listing row.

The thing being defended here is that a summary is *obviously* a summary. A row
that merely looks smaller invites someone to write it back, and writing it back
destroys every facet payload it dropped.
"""

from __future__ import annotations

import json

import pytest

from iotsploit_core.domain.summary import SUMMARY_FLAG, summarize_component, summarize_target

pytestmark = pytest.mark.unit


def component(**kwargs):
    base = dict(
        component_id="c_gw",
        name="Gateway",
        type="ecu",
        status="active",
        facets={
            "can": {
                "bus_id": "bus_powertrain_can",
                "node": "Gateway_MQB",
                "messages": [{"frame_id": i, "signals": [1, 2, 3]} for i in range(35)],
            },
            "doip": {"logical_address": 16, "port": 13400},
        },
        properties={"note": "hi"},
    )
    base.update(kwargs)
    return base


def target(**kwargs):
    base = dict(
        target_id="vw_golf_mqb",
        name="VW Golf",
        type="vehicle",
        status="active",
        components=[component()],
        buses=[{"bus_id": "bus_powertrain_can", "name": "Powertrain CAN", "type": "can",
                "properties": {"messages": [{"frame_id": 981}]}}],
        edges=[{"source": "c_gw", "target": "bus_powertrain_can", "relation": "bus_member"}],
    )
    base.update(kwargs)
    return base


def test_a_facet_list_is_replaced_by_its_size():
    row = summarize_component(component())

    assert "messages" not in row["facets"]["can"]
    assert row["facet_sizes"]["can"]["messages"] == 35


def test_scalar_facet_fields_survive():
    """The address is what the listing is for; only the bulk goes."""
    row = summarize_component(component())

    assert row["facets"]["can"]["bus_id"] == "bus_powertrain_can"
    assert row["facets"]["doip"] == {"logical_address": 16, "port": 13400}


def test_a_facet_with_nothing_bulk_reports_no_sizes():
    row = summarize_component(component(facets={"doip": {"logical_address": 16}}))

    assert "facet_sizes" not in row


def test_an_unregistered_facet_is_summarized_like_any_other():
    """Core cannot tell the difference, and a raw payload is just as large.

    The key is fictional on purpose: naming a real protocol here would stop
    testing the unregistered path as soon as that protocol's facet shipped.
    """
    row = summarize_component(component(facets={"not_a_real_protocol": {"services": [1, 2, 3], "host": "h"}}))

    assert row["facets"]["not_a_real_protocol"] == {"host": "h"}
    assert row["facet_sizes"]["not_a_real_protocol"]["services"] == 3


def test_subclass_fields_survive():
    """The device screens read adb_serial_id straight off the listing."""
    row = summarize_component(component(type="adb_device", adb_serial_id="ABC123", facets={}))

    assert row["adb_serial_id"] == "ABC123"


def test_component_properties_become_a_count():
    row = summarize_component(component())

    assert "properties" not in row
    assert row["property_count"] == 1


def test_a_summary_says_so():
    """Without this flag nothing downstream can refuse to write the row back."""
    assert summarize_target(target())[SUMMARY_FLAG] is True


def test_counts_describe_what_was_dropped():
    row = summarize_target(target())

    assert row["component_count"] == 1
    assert row["bus_count"] == 1
    assert row["edge_count"] == 1
    assert row["facet_item_count"] == 35


def test_bus_identity_survives_but_its_payload_does_not():
    """A DBC import parks unsent frames in bus properties. That is bulk too."""
    bus = summarize_target(target())["buses"][0]

    assert bus["bus_id"] == "bus_powertrain_can" and bus["name"] == "Powertrain CAN"
    assert "properties" not in bus


def test_edges_are_kept_whole():
    """They are the topology, they are small, and the graph needs all of them."""
    assert summarize_target(target())["edges"] == target()["edges"]


def test_identity_fields_are_untouched():
    row = summarize_target(target(ip_address="10.0.0.1", location="bench"))

    assert row["target_id"] == "vw_golf_mqb"
    assert row["ip_address"] == "10.0.0.1"
    assert row["location"] == "bench"


def test_the_projection_is_smaller_by_the_order_of_magnitude_that_motivated_it():
    """Sized like the VW MQB fixture: 19 ECUs whose frames carry real signals.

    The toy frames used elsewhere in this file are too small to show the effect
    the projection exists for -- the bulk is in the signal rows, not the frames.
    """
    signal = {"name": "BCM1_Fernlicht_Anf", "start_bit": 16, "length": 1,
              "byte_order": "little", "signed": False, "factor": 1.0, "offset": 0.0,
              "minimum": 0.0, "maximum": 1.0, "unit": "", "multiplexer": None}
    frames = [{"frame_id": i, "name": f"Frame_{i}", "dlc": 8, "is_extended": False,
               "signals": [dict(signal) for _ in range(12)]} for i in range(35)]
    big = target(components=[
        component(component_id=f"c{i}",
                  facets={"can": {"bus_id": "b", "node": f"N{i}", "messages": frames}})
        for i in range(19)
    ])

    before = len(json.dumps(big))
    after = len(json.dumps(summarize_target(big)))

    assert after * 10 < before


def test_summarizing_does_not_mutate_the_argument():
    original = target()
    snapshot = json.dumps(original)

    summarize_target(original)

    assert json.dumps(original) == snapshot


def test_a_target_with_no_topology_still_projects():
    row = summarize_target({"target_id": "t", "name": "T", "type": "generic"})

    assert row["component_count"] == 0
    assert row["bus_count"] == 0
    assert row["edge_count"] == 0
    assert row["facet_item_count"] == 0
