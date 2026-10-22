"""Resolving a target's CAN frames, and refusing to guess between two answers.

Three rules are what these tests exist to protect, because breaking any of them
produces a frame that looks right and is not:

*A frame's identity is its bus, its number, and its extended flag.* Drop any
part and a resolver answers confidently about the wrong wire.

*Two documents disagreeing about one identity is a finding.* Choosing the first
would transmit one document's frame while the operator read the other's, with
nothing on screen to say so.

*Reading a target never changes it.* The snapshot a plugin holds is shared with
the caller that built it.
"""

from __future__ import annotations

import copy

import pytest

from iotsploit_protocols.canbus import TargetCanCatalog
from iotsploit_protocols.canbus.errors import CanDefinitionError

pytestmark = pytest.mark.unit

POWERTRAIN = "bus_can_powertrain"
BODY = "bus_can_body"


@pytest.fixture
def catalog(target):
    return TargetCanCatalog.from_target(target)


# ── what gets collected ───────────────────────────────────────────────


def test_only_can_buses_are_collected(catalog):
    """The Ethernet bus in the fixture carries a `messages` list too. Reading it
    would put frames on a bus that cannot carry them."""
    assert [bus.bus_id for bus in catalog.buses] == [POWERTRAIN, BODY]


def test_both_storage_locations_land_on_one_bus(catalog):
    """ARXML writes frames under the bus, DBC writes them under the component
    that sends them. One wire, so one list."""
    owners = {frame.name: frame.owner_kind for frame in catalog.frames(POWERTRAIN)}

    assert owners["VehicleStatus"] == "bus"
    assert owners["BmsStatus"] == "component"


def test_a_component_frame_keeps_the_component_it_came_from(catalog):
    """Provenance is what lets a diagnostic say which document to fix."""
    frame = catalog.resolve(POWERTRAIN, 0x2B0)

    assert frame.component_id == "c_bms"
    assert frame.component_name == "Battery Management"
    assert frame.senders == ("BMS",)


def test_a_component_facet_on_another_bus_is_not_collected(catalog):
    """The gateway's facet names the body bus. Its frames are not powertrain
    frames however close the components sit on the diagram."""
    assert all(f.component_id != "c_gateway" for f in catalog.frames(POWERTRAIN))


def test_a_component_owned_frame_resolves_with_its_value_table(catalog):
    """The half that used to be impossible: the stored facet could not hold
    choices, so a labelled component frame arrived as bare numbers."""
    frame = catalog.resolve(POWERTRAIN, 0x2B0)
    mode = frame.signal("PackMode")

    assert mode is not None
    assert mode.choices == {0: "Idle", 1: "Charging", 2: "Discharging", 3: "Fault"}


def test_string_keyed_choices_are_normalized_to_integers(catalog):
    """The ARXML importer stringifies mapping keys on its way to JSON. Left
    alone, "0" and 0 become two codes for one value."""
    frame = catalog.resolve(POWERTRAIN, 0x123)

    assert frame.signal("IgnitionState").choices == {
        0: "Off",
        1: "Acc",
        2: "On",
        3: "Crank",
    }


# ── identity ──────────────────────────────────────────────────────────


def test_the_same_number_on_two_buses_is_two_frames(catalog):
    """0x123 is VehicleStatus on one bus and BodyStatus on the other. Neither
    is ambiguous once the bus is named."""
    assert catalog.resolve(POWERTRAIN, 0x123).name == "VehicleStatus"
    assert catalog.resolve(BODY, 0x123).name == "BodyStatus"


def test_standard_and_extended_forms_of_one_number_stay_distinct(catalog):
    """Different frames sharing a wire, so the flag is part of the identity."""
    standard = catalog.resolve(POWERTRAIN, 0x123, is_extended=False)
    extended = catalog.resolve(POWERTRAIN, 0x123, is_extended=True)

    assert standard.name == "VehicleStatus"
    assert extended.name == "VehicleStatusExtended"
    assert standard.dlc != extended.dlc


def test_asking_for_a_frame_on_the_wrong_bus_fails(catalog):
    """BrakeData exists, but not here. Falling back to a target-wide search
    would send powertrain bytes to the body bus."""
    with pytest.raises(CanDefinitionError, match="documents no standard frame 0x2A1"):
        catalog.resolve(BODY, 0x2A1)


def test_an_unknown_bus_names_the_buses_that_do_exist(catalog):
    with pytest.raises(CanDefinitionError, match="bus_can_body"):
        catalog.resolve("bus_can_chassis", 0x123)


@pytest.mark.parametrize(
    "frame_id, is_extended",
    [(0x800, False), (0x20000000, True), (-1, False)],
)
def test_a_frame_id_too_wide_for_its_flag_is_refused(catalog, frame_id, is_extended):
    """0x800 does not fit 11 bits. Truncating it silently addresses a different
    ECU than the one on screen."""
    with pytest.raises(CanDefinitionError, match="does not fit"):
        catalog.resolve(POWERTRAIN, frame_id, is_extended=is_extended)


# ── the name is a staleness check, not a key ──────────────────────────


def test_a_stale_frame_name_fails_rather_than_encoding(catalog):
    """A form built before a re-import may hold a name this id no longer has.
    Encoding anyway sends the right bytes for the wrong frame."""
    with pytest.raises(CanDefinitionError, match="the target changed"):
        catalog.resolve(POWERTRAIN, 0x123, expected_name="OldName")


def test_a_matching_name_resolves(catalog):
    assert catalog.resolve(POWERTRAIN, 0x123, expected_name="VehicleStatus").dlc == 8


# ── duplicates and conflicts ──────────────────────────────────────────


def test_identical_duplicates_collapse_to_one_frame(target, brake_frame):
    """Two components declaring one frame the same way is ordinary. Treating it
    as a conflict would make most real DBCs unusable."""
    target["components"][0]["facets"]["can"]["messages"].append(brake_frame)

    catalog = TargetCanCatalog.from_target(target)
    matches = [f for f in catalog.frames(POWERTRAIN) if f.frame_id == 0x2A1]

    assert len(matches) == 1
    assert catalog.bus(POWERTRAIN).conflicts == ("s600",)


def test_definitions_that_disagree_are_a_conflict_not_a_choice(catalog):
    """The fixture declares 0x600 as 8 bytes on the bus and 4 on the component."""
    with pytest.raises(CanDefinitionError, match="conflicting definitions"):
        catalog.resolve(POWERTRAIN, 0x600)


def test_a_conflicted_frame_is_still_listed_with_its_reason(catalog):
    """Omitting it leaves the operator wondering where the frame went; showing
    it disabled says which two documents to reconcile."""
    frame = catalog.bus(POWERTRAIN).frame(0x600, False)

    assert frame is not None
    assert frame.is_supported is False
    assert "incompatible definitions" in frame.unsupported_reason
    assert "Battery Management" in frame.unsupported_reason


def test_provenance_alone_is_not_a_conflict(target, brake_frame):
    """Who sends a frame and how often does not change its bytes."""
    brake_frame["senders"] = ["SomeoneElse"]
    brake_frame["cycle_time_ms"] = 999
    target["components"][0]["facets"]["can"]["messages"].append(brake_frame)

    catalog = TargetCanCatalog.from_target(target)

    assert catalog.resolve(POWERTRAIN, 0x2A1).name == "BrakeData"


# ── unsupported shapes ────────────────────────────────────────────────


def test_a_container_frame_is_refused_with_a_stable_reason(catalog):
    """Header selection and per-PDU encoding are a separate design. Refusing is
    honest; encoding the outer frame's empty payload is not."""
    with pytest.raises(CanDefinitionError, match="container frame"):
        catalog.resolve(POWERTRAIN, 0x500)


def test_a_classic_frame_longer_than_eight_bytes_is_refused(target):
    target["buses"][0]["properties"]["messages"].append(
        {"frame_id": 0x701, "name": "TooLong", "dlc": 16, "is_fd": False, "signals": []}
    )

    catalog = TargetCanCatalog.from_target(target)

    with pytest.raises(CanDefinitionError, match="at most 8 bytes"):
        catalog.resolve(POWERTRAIN, 0x701)


def test_an_fd_frame_with_an_impossible_length_is_refused(target):
    """CAN FD keeps 0..8 and then jumps. There is no 9-byte FD frame."""
    target["buses"][0]["properties"]["messages"].append(
        {"frame_id": 0x702, "name": "OddFd", "dlc": 9, "is_fd": True, "signals": []}
    )

    catalog = TargetCanCatalog.from_target(target)

    with pytest.raises(CanDefinitionError, match="no 9-byte payload"):
        catalog.resolve(POWERTRAIN, 0x702)


def test_branch_signals_without_a_switch_are_refused(target):
    """Nothing says which branch is live, so no set of values is complete."""
    orphan = copy.deepcopy(target["buses"][0]["properties"]["messages"][3])
    orphan["frame_id"] = 0x703
    orphan["name"] = "Headless"
    orphan["signals"] = [s for s in orphan["signals"] if s.get("multiplexer") != "M"]
    target["buses"][0]["properties"]["messages"].append(orphan)

    catalog = TargetCanCatalog.from_target(target)

    with pytest.raises(CanDefinitionError, match="no signal is marked as the switch"):
        catalog.resolve(POWERTRAIN, 0x703)


# ── purity ────────────────────────────────────────────────────────────


def test_building_a_catalogue_does_not_touch_the_target(target):
    """The snapshot is shared with whoever built it."""
    before = copy.deepcopy(target)

    TargetCanCatalog.from_target(target)

    assert target == before
