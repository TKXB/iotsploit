"""Reading a DBC, and folding it onto a target.

The fixture is written here rather than vendored so the tests can exercise
shapes the one real file happens not to use -- extended ids, multiplexed and
big-endian signals, a frame nobody sends -- and so no third-party file's
licence has to be reasoned about to run the suite.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_core.domain.target import ComponentFactory, Vehicle  # noqa: E402
from iotsploit_django.tools.can_facet import FACET_KEY, CanFacet  # noqa: E402
from iotsploit_django.tools.dbc import apply_dbc, component_id_for, parse_dbc  # noqa: E402

pytestmark = pytest.mark.unit

DBC = """VERSION "1.0"


NS_ :
    CM_
    BA_DEF_

BS_:
BU_: BMS VCU
BO_ 151 BMS_Monitoring: 8 BMS
   SG_ BMS_VOLTAGE : 24|12@1+ (0.5,-100) [0|600] "V" Vector__XXX
   SG_ BMS_MODE M : 0|2@1+ (1,0) [0|3] "" VCU
   SG_ BMS_TEMP m1 : 8|8@0- (1,-40) [-40|215] "degC" VCU

BO_ 2147488308 VCU_Extended: 8 VCU
   SG_ VCU_TORQUE : 0|16@1- (0.1,0) [0|0] "Nm" Vector__XXX

BO_ 512 Orphan_Frame: 4 Vector__XXX
   SG_ ORPHAN_BIT : 0|1@1+ (1,0) [0|1] "" Vector__XXX

BA_DEF_ BO_ "GenMsgBackgroundColor" STRING ;
BA_DEF_DEF_ "GenMsgBackgroundColor" "#ffffff";
CM_ BU_ BMS "Battery management, high voltage side";
VAL_ 151 BMS_MODE 0 "Idle" 1 "Charging" 2 "Discharging" 3 "Fault" ;
"""


def golf():
    return {"target_id": "vw_golf_gte", "name": "VW Golf GTE", "type": "vehicle"}


def imported(**kwargs):
    return apply_dbc(golf(), DBC, bus_id="bus_can", **kwargs)


def facet_of(target, component_id):
    component = next(c for c in target["components"] if c["component_id"] == component_id)
    return component["facets"][FACET_KEY]


# ── parsing ───────────────────────────────────────────────────────────


def test_nodes_come_back_in_declaration_order():
    """Also proves nothing else on a line beginning with a keyword is mistaken
    for a node: BA_DEF_ and friends would show up here if they were."""
    assert [n.name for n in parse_dbc(DBC).nodes] == ["BMS", "VCU"]


def test_a_frame_lands_on_the_node_that_sends_it():
    bms = parse_dbc(DBC).nodes[0]

    assert [m.name for m in bms.messages] == ["BMS_Monitoring"]
    assert bms.messages[0].frame_id == 0x97
    assert bms.messages[0].dlc == 8


def test_an_extended_id_keeps_its_flag_out_of_the_id():
    """Bit 31 is a marker, not part of the address; leaving it in would make
    the id unrecognisable next to anything a sniffer prints."""
    vcu = parse_dbc(DBC).nodes[1]

    assert vcu.messages[0].frame_id == 0x1234
    assert vcu.messages[0].is_extended is True


def test_a_standard_id_is_not_marked_extended():
    assert parse_dbc(DBC).nodes[0].messages[0].is_extended is False


def test_a_signal_layout_is_read_off_the_line():
    voltage = parse_dbc(DBC).nodes[0].messages[0].signals[0]

    assert voltage.name == "BMS_VOLTAGE"
    assert (voltage.start_bit, voltage.length) == (24, 12)
    assert voltage.byte_order == "little"
    assert voltage.signed is False
    assert (voltage.factor, voltage.offset) == (0.5, -100.0)
    assert voltage.unit == "V"


def test_a_motorola_signal_is_labelled_big_endian():
    temp = parse_dbc(DBC).nodes[0].messages[0].signals[2]

    assert temp.byte_order == "big"
    assert temp.signed is True


def test_a_stated_range_is_kept():
    voltage = parse_dbc(DBC).nodes[0].messages[0].signals[0]

    assert (voltage.minimum, voltage.maximum) == (0.0, 600.0)


def test_zero_to_zero_is_no_range_at_all():
    """DBC writes [0|0] for "unspecified". Storing it literally would claim the
    signal is always zero, and anything range-checking would reject every
    sample."""
    torque = parse_dbc(DBC).nodes[1].messages[0].signals[0]

    assert torque.minimum is None
    assert torque.maximum is None


def test_a_multiplexer_token_is_kept():
    signals = parse_dbc(DBC).nodes[0].messages[0].signals

    assert signals[1].multiplexer == "M"
    assert signals[2].multiplexer == "m1"
    assert signals[0].multiplexer is None


def test_a_frame_with_no_transmitter_is_not_given_one():
    contents = parse_dbc(DBC)

    assert [m.name for m in contents.unsent] == ["Orphan_Frame"]
    assert "Vector__XXX" not in [n.name for n in contents.nodes]


def test_signals_do_not_leak_between_frames():
    contents = parse_dbc(DBC)
    sent = [m for node in contents.nodes for m in node.messages]

    assert [len(m.signals) for m in sent] == [3, 1]
    assert [len(m.signals) for m in contents.unsent] == [1]


def test_the_no_sender_placeholder_is_not_a_node_even_when_declared():
    """Real files list Vector__XXX in BU_. Taking that at face value put every
    unsent frame on a component and on the bus, the same frame twice."""
    text = 'BU_: BMS Vector__XXX\nBO_ 16 X: 1 Vector__XXX\n   SG_ S : 0|1@1+ (1,0) [0|0] "" Vector__XXX\n'

    contents = parse_dbc(text)

    assert [n.name for n in contents.nodes] == ["BMS"]
    assert [m.name for m in contents.unsent] == ["X"]


def test_an_undeclared_transmitter_still_becomes_a_node():
    """A malformed DBC, but "BO_ ... : 8 GATEWAY" says what it means."""
    text = "BU_: BMS\nBO_ 16 Gw_Status: 1 GATEWAY\n"

    assert [n.name for n in parse_dbc(text).nodes] == ["BMS", "GATEWAY"]


def test_a_dlc_is_taken_as_written():
    """Hand-written DBCs declare 0 and lay out eight bytes anyway. Guessing
    would turn the file's mistake into ours."""
    text = 'BU_: BMS\nBO_ 16 X: 0 BMS\n   SG_ S : 63|1@1+ (1,0) [0|0] "" Vector__XXX\n'

    assert parse_dbc(text).nodes[0].messages[0].dlc == 0


# ── value tables ──────────────────────────────────────────────────────


def test_a_value_table_lands_on_the_signal_it_names():
    """Without this a composer can only offer the raw number, and a decoded
    capture reports 3 rather than what 3 means."""
    mode = parse_dbc(DBC).nodes[0].messages[0].signals[1]

    assert mode.name == "BMS_MODE"
    assert mode.choices == {0: "Idle", 1: "Charging", 2: "Discharging", 3: "Fault"}


def test_a_signal_with_no_value_table_has_none():
    """None, not an empty dict: "nobody labelled this" and "this is labelled
    with nothing" are different claims about the file."""
    assert parse_dbc(DBC).nodes[0].messages[0].signals[0].choices is None


def test_a_value_table_is_matched_within_its_own_frame():
    """A signal name is only unique inside a frame. AliveCounter is on half the
    frames of a real bus, and one frame's labels are not another's."""
    text = (
        'BU_: A\n'
        'BO_ 100 First: 1 A\n'
        '   SG_ State : 0|2@1+ (1,0) [0|3] "" Vector__XXX\n'
        'BO_ 200 Second: 1 A\n'
        '   SG_ State : 0|2@1+ (1,0) [0|3] "" Vector__XXX\n'
        'VAL_ 100 State 0 "Off" 1 "On" ;\n'
    )

    first, second = parse_dbc(text).nodes[0].messages

    assert first.signals[0].choices == {0: "Off", 1: "On"}
    assert second.signals[0].choices is None


def test_a_value_table_finds_an_extended_frame_by_its_masked_id():
    """VAL_ repeats the raw id with bit 31 set, exactly as BO_ writes it, so
    both sides have to be masked or an extended frame never matches."""
    text = (
        'BU_: A\n'
        'BO_ 2147483748 Ext: 1 A\n'
        '   SG_ Mode : 0|2@1+ (1,0) [0|3] "" Vector__XXX\n'
        'VAL_ 2147483748 Mode 1 "Armed" ;\n'
    )

    message = parse_dbc(text).nodes[0].messages[0]

    assert message.is_extended is True
    assert message.signals[0].choices == {1: "Armed"}


def test_a_negative_code_is_kept():
    """A signed signal's table legitimately labels -1, and a pattern that only
    matched digits would silently drop that row and keep the rest."""
    text = (
        'BU_: A\n'
        'BO_ 100 Frame: 1 A\n'
        '   SG_ Trim : 0|8@1- (1,0) [-128|127] "" Vector__XXX\n'
        'VAL_ 100 Trim -1 "Retard" 0 "Neutral" 1 "Advance" ;\n'
    )

    assert parse_dbc(text).nodes[0].messages[0].signals[0].choices == {
        -1: "Retard",
        0: "Neutral",
        1: "Advance",
    }


def test_a_dangling_value_table_warns_instead_of_guessing():
    """A malformed file is still worth importing. Attaching this table to some
    other signal would invent a meaning the file never assigned."""
    text = (
        'BU_: A\n'
        'BO_ 100 Frame: 1 A\n'
        '   SG_ Mode : 0|2@1+ (1,0) [0|3] "" Vector__XXX\n'
        'VAL_ 999 Missing 0 "Nope" ;\n'
    )

    contents = parse_dbc(text)

    assert contents.nodes[0].messages[0].signals[0].choices is None
    assert len(contents.warnings) == 1
    assert "0x3E7" in contents.warnings[0]
    assert "Missing" in contents.warnings[0]


def test_an_environment_variable_table_is_not_read_as_a_frame():
    """VAL_ has a second form naming an environment variable where the frame id
    goes. It describes nothing on the wire."""
    text = (
        'BU_: A\n'
        'BO_ 100 Frame: 1 A\n'
        '   SG_ Mode : 0|2@1+ (1,0) [0|3] "" Vector__XXX\n'
        'VAL_ EnvBrakePedal 0 "Released" 1 "Pressed" ;\n'
    )

    contents = parse_dbc(text)

    assert contents.warnings == []
    assert contents.nodes[0].messages[0].signals[0].choices is None


def test_a_value_table_survives_the_round_trip_into_a_component():
    """The path that used to lose it: the facet model dropped unknown keys, so
    a table parsed here vanished the moment it was loaded back."""
    data = imported()
    component = ComponentFactory.create_component(data["components"][0])

    mode = next(s for s in component.facet(FACET_KEY).messages[0].signals if s.name == "BMS_MODE")
    assert mode.choices == {0: "Idle", 1: "Charging", 2: "Discharging", 3: "Fault"}


# ── folding onto a target ─────────────────────────────────────────────


def test_the_bus_is_created_with_the_name_it_was_given():
    buses = imported(bus_name="Hybrid CAN")["buses"]

    assert len(buses) == 1
    assert (buses[0]["bus_id"], buses[0]["name"], buses[0]["type"]) == (
        "bus_can",
        "Hybrid CAN",
        "can",
    )


def test_each_node_becomes_a_component_carrying_its_frames():
    target = imported()

    assert [c["name"] for c in target["components"]] == ["BMS", "VCU"]
    assert facet_of(target, component_id_for("BMS"))["messages"][0]["name"] == "BMS_Monitoring"


def test_the_facet_names_the_bus_and_the_node_it_came_from():
    facet = facet_of(imported(), component_id_for("VCU"))

    assert facet["bus_id"] == "bus_can"
    assert facet["node"] == "VCU"


def test_every_node_is_wired_to_the_bus():
    target = imported()

    assert target["edges"] == [
        {"source": "c_bms", "target": "bus_can", "relation": "bus_member", "properties": {}},
        {"source": "c_vcu", "target": "bus_can", "relation": "bus_member", "properties": {}},
    ]


def test_a_frame_nobody_sends_belongs_to_the_bus():
    """It is a fact about the wire, and there is no component to hang it on."""
    bus = imported()["buses"][0]

    assert [m["name"] for m in bus["properties"]["messages"]] == ["Orphan_Frame"]


def test_a_node_comment_becomes_a_description():
    component = next(c for c in imported()["components"] if c["component_id"] == "c_bms")

    assert component["properties"]["description"].startswith("Battery management")


def test_applying_the_same_file_twice_changes_nothing():
    """There is no import bookkeeping anywhere else, so re-running has to be
    the thing that stays safe."""
    once = imported()
    twice = apply_dbc(once, DBC, bus_id="bus_can")

    assert twice == once


def test_a_second_import_replaces_the_frames_rather_than_appending():
    target = apply_dbc(imported(), DBC.replace("BMS_Monitoring", "BMS_Status"), bus_id="bus_can")
    frames = facet_of(target, "c_bms")["messages"]

    assert [m["name"] for m in frames] == ["BMS_Status"]


def test_a_renamed_component_is_found_by_the_node_it_stores():
    """Renaming a component to something readable must not fork it in two on
    the next import."""
    target = imported()
    next(c for c in target["components"] if c["component_id"] == "c_bms")["name"] = "Battery Pack"

    again = apply_dbc(target, DBC, bus_id="bus_can")

    assert [c["name"] for c in again["components"]] == ["Battery Pack", "VCU"]


def test_the_argument_is_not_modified():
    original = golf()

    apply_dbc(original, DBC, bus_id="bus_can")

    assert original == {"target_id": "vw_golf_gte", "name": "VW Golf GTE", "type": "vehicle"}


def test_existing_components_and_buses_are_left_alone():
    target = apply_dbc(
        {
            "target_id": "vw_golf_gte",
            "name": "VW Golf GTE",
            "type": "vehicle",
            "components": [{"component_id": "c_tcam", "name": "TCAM", "type": "ecu"}],
            "buses": [{"bus_id": "bus_eth", "name": "Ethernet", "type": "ethernet"}],
        },
        DBC,
        bus_id="bus_can",
    )

    assert [c["component_id"] for c in target["components"]] == ["c_tcam", "c_bms", "c_vcu"]
    assert [b["bus_id"] for b in target["buses"]] == ["bus_eth", "bus_can"]


# ── the result has to be a target ─────────────────────────────────────


def test_the_result_hydrates_into_a_target_whose_edges_validate():
    """The whole point of deriving component ids: bus_member edges resolve."""
    data = imported(bus_name="Hybrid CAN")

    target = Vehicle(
        target_id=data["target_id"],
        name=data["name"],
        type="vehicle",
        components=[ComponentFactory.create_component(c) for c in data["components"]],
        buses=data["buses"],
        edges=data["edges"],
    )

    assert [e.relation for e in target.edges] == ["bus_member", "bus_member"]


def test_the_stored_payload_resolves_back_to_a_can_facet():
    """Not a RawFacet: a payload that no longer validates would be kept, but
    silently, and every frame would stop being readable as one."""
    data = imported()
    component = ComponentFactory.create_component(data["components"][0])

    facet = component.facet(FACET_KEY)
    assert isinstance(facet, CanFacet)
    assert facet.messages[0].signals[0].name == "BMS_VOLTAGE"


def test_a_round_trip_through_the_component_keeps_every_signal():
    """The path a UI save takes: dump, ship as JSON, hydrate, dump again."""
    data = imported()
    once = ComponentFactory.create_component(data["components"][0]).model_dump()
    twice = ComponentFactory.create_component(once).model_dump()

    assert twice["facets"][FACET_KEY] == data["components"][0]["facets"][FACET_KEY]


# ── and the catalogue has to be able to read it back ──────────────────


def test_an_imported_frame_resolves_and_encodes_through_the_stored_facet():
    """The whole path, end to end: DBC text, stored facet, hydrated component,
    catalogue, encoder.

    Asserted through a round-tripped facet rather than a hand-built dict on
    purpose. The failure this guards against is silent -- a field the stored
    model does not declare is dropped on load, and a dropped value table turns
    a named signal into one that cannot be encoded by name at all. Building the
    dict by hand would skip exactly the step that loses it.
    """
    from iotsploit_protocols.canbus import TargetCanCatalog, decode_frame, encode_frame

    data = imported()
    # Hydrate and dump, which is the round trip a UI save performs.
    data["components"] = [
        ComponentFactory.create_component(c).model_dump() for c in data["components"]
    ]

    catalog = TargetCanCatalog.from_target(data)
    frame = catalog.resolve("bus_can", 0x97, expected_name="BMS_Monitoring")

    assert frame.owner_kind == "component"
    assert frame.signal("BMS_MODE").choices == {
        0: "Idle",
        1: "Charging",
        2: "Discharging",
        3: "Fault",
    }

    # "Charging" is code 1, which selects the m1 branch, so BMS_TEMP is part
    # of this frame and leaving it out is an error rather than a zero.
    encoded = encode_frame(
        frame, {"BMS_VOLTAGE": "0", "BMS_MODE": "Charging", "BMS_TEMP": "-40"}
    )
    decoded = decode_frame(frame, encoded.data)

    assert decoded.ok is True
    assert decoded.signals["BMS_MODE"] == "Charging"
    assert decoded.signals["BMS_TEMP"] == -40


def test_a_bus_owned_and_a_component_owned_frame_resolve_the_same_way():
    """The two storage locations are a historical accident, not a distinction
    any consumer should have to know about."""
    from iotsploit_protocols.canbus import TargetCanCatalog

    catalog = TargetCanCatalog.from_target(imported())

    component_owned = catalog.resolve("bus_can", 0x97)
    bus_owned = catalog.resolve("bus_can", 0x200)

    assert component_owned.owner_kind == "component"
    assert bus_owned.owner_kind == "bus"
    assert component_owned.is_supported and bus_owned.is_supported
    assert {s.name for s in bus_owned.signals} == {"ORPHAN_BIT"}
