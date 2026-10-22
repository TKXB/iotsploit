"""Rendering and dispatch for `target list`.

The listing is how an operator confirms which vehicle they are pointed at before
running anything against it, so the parts asserted here are the ones that cause
real mistakes when wrong: the active-target marker, and the configuration a
plugin will actually read being visible at all.
"""

import io
from datetime import datetime

import cmd2
import pytest

from iotsploit_cli.commands.resource_commands import ResourceCommands
from iotsploit_cli.commands.target_commands import TargetCommands

pytestmark = pytest.mark.unit

TARGETS = [
    {
        "target_id": "zeekr_demo_001",
        "name": "Zeekr 001 (demo bench)",
        "type": "vehicle",
        "status": "active",
        "ip_address": "192.168.50.10",
        "location": "Lab bench 3",
        "properties": {"model_year": 2025},
        "components": [
            {
                "component_id": "comp_tcam_001", "name": "TCAM", "type": "adb_device", "status": "active",
                "adb_serial_id": "ZK2025TCAM000001", "properties": {"ip_address": "198.18.34.1"},
                "facets": {"doip": {"logical_address": 4113, "tester_address": 3712, "port": 13400}},
            },
            {
                "component_id": "comp_vgm_001", "name": "VGM", "type": "ecu", "status": "inactive",
                "properties": {"doip_logical_address": "0x1001"},
            },
        ],
        "buses": [{"bus_id": "bus_can_b", "name": "CAN-B", "type": "can", "properties": {"baud": 500000}}],
        "edges": [{"source": "comp_tcam_001", "target": "bus_can_b", "relation": "bus_member"}],
        "updated_at": "2026-08-12T10:19:33",
    },
    {
        "target_id": "bare_001",
        "name": "Bare Target",
        "type": "iot",
        "status": "active",
        "ip_address": None,
        "location": None,
        "properties": {},
        "components": [],
    },
]

#: A DBC import, in the shape it comes back out of the database. The facet is
#: the case that used to render as four kilobytes of dict repr.
GOLF = {
    "target_id": "vw_golf_gte",
    "name": "VW Golf GTE",
    "type": "vehicle",
    "status": "active",
    "ip_address": None,
    "location": None,
    "properties": {"model": "Golf GTE (Mk7 PHEV)"},
    "components": [
        {
            "component_id": "c_hv_battery_hybridcan",
            "name": "HV_Battery_HybridCan",
            "type": "ecu",
            "status": "active",
            "properties": {"description": "Messages from the HV battery"},
            "facets": {
                "can": {
                    "bus_id": "bus_hybrid_can",
                    "node": "HV_Battery_HybridCan",
                    "messages": [
                        {
                            "frame_id": 151,
                            "name": "BMS_Monitoring",
                            "signals": [{"name": f"S{i}", "start_bit": i} for i in range(20)],
                        }
                    ],
                }
            },
        }
    ],
    "buses": [{"bus_id": "bus_hybrid_can", "name": "Hybrid CAN", "type": "can", "properties": {}}],
    "edges": [{"source": "c_hv_battery_hybridcan", "target": "bus_hybrid_can", "relation": "bus_member"}],
}


class FakeTargetManager:
    def __init__(self, targets, current_id=None):
        self._targets = targets
        self._current_id = current_id

    def get_all_targets(self):
        return self._targets

    def get_current_target(self):
        if self._current_id is None:
            return None
        selected = next((t for t in self._targets if t["target_id"] == self._current_id), None)
        name = selected["name"] if selected else self._current_id
        return type("T", (), {"target_id": self._current_id, "name": name})()


class TargetShell(cmd2.Cmd, TargetCommands, ResourceCommands):
    def __init__(self, targets=TARGETS, current_id="zeekr_demo_001"):
        super().__init__()
        self._canonical_command_registry = True
        self.target_manager = FakeTargetManager(targets, current_id)


def output(command, **kwargs):
    """Run a command and return its output with styling stripped."""
    shell = TargetShell(**kwargs)
    shell.stdout = io.StringIO()
    shell.onecmd_plus_hooks(command)
    return cmd2.ansi.strip_style(shell.stdout.getvalue())


def test_summary_lists_every_target_with_counts():
    text = output("target list")

    assert "Targets (2)" in text
    assert "zeekr_demo_001" in text and "bare_001" in text
    # Components and buses: the two lists a target is made of. The interface
    # count that used to sit here counted a list that no longer exists.
    zeekr_row = next(line for line in text.splitlines() if "zeekr_demo_001" in line)
    assert zeekr_row.split()[-2:] == ["2", "1"]


def test_summary_marks_the_active_target():
    """Running a plugin against the wrong vehicle is the mistake this prevents."""
    text = output("target list")
    zeekr_row = next(line for line in text.splitlines() if "zeekr_demo_001" in line)
    bare_row = next(line for line in text.splitlines() if "bare_001" in line)

    assert zeekr_row.lstrip().startswith("*")
    assert not bare_row.lstrip().startswith("*")


def test_summary_shows_a_placeholder_for_missing_ip_and_location():
    bare_row = next(line for line in output("target list").splitlines() if "bare_001" in line)
    assert " - " in bare_row


def test_detail_shows_components():
    text = output("target list zeekr_demo_001")

    assert "Components (2)" in text
    assert "TCAM" in text and "comp_tcam_001" in text
    assert "ZK2025TCAM000001" in text  # type-specific field
    assert "ip_address=198.18.34.1" in text  # free-form property
    assert "model_year" in text


def test_detail_shows_the_configuration_a_driver_will_read():
    """A facet is what DoIP_Mgr actually looks up, so it needs to be visible
    before a plugin is run, not only in the UI."""
    text = output("target list zeekr_demo_001")

    assert "Facets (1)" in text
    assert "doip" in text
    assert "logical_address=4113" in text


def test_detail_shows_the_buses_and_how_things_are_wired():
    text = output("target list zeekr_demo_001")

    assert "Buses (1)" in text
    assert "CAN-B" in text and "bus_can_b" in text
    assert "Edges (1)" in text
    assert "comp_tcam_001  --bus_member->  bus_can_b" in text


def test_a_target_with_no_topology_says_nothing_about_it():
    """Otherwise every listing carries three empty sections."""
    text = output("target list bare_001")

    assert "Facets" not in text
    assert "Buses" not in text
    assert "Edges" not in text


def test_an_imported_network_is_summarised_rather_than_dumped():
    """Twenty signals rendered as a dict filled the column with Python syntax
    and were then cut off mid-token."""
    text = output("target list vw_golf_gte", targets=[GOLF], current_id="vw_golf_gte")

    assert "can" in text
    assert "bus_id=bus_hybrid_can" in text
    assert "messages=1 item" in text
    assert "'signals'" not in text and "frame_id" not in text


def test_detail_accepts_a_name_as_well_as_an_id():
    assert "Components (2)" in output("target list 'Zeekr 001 (demo bench)'")


def test_detail_for_all_targets_renders_empty_collections():
    text = output("target list all")

    assert text.count("Components (") == 2
    assert "Components (0)" in text
    assert "none" in text


def test_unknown_target_reports_an_error_and_lists_nothing():
    text = output("target list does_not_exist")
    assert "Components (" not in text


def test_empty_database_reports_cleanly():
    text = output("target list", targets=[], current_id=None)
    assert "No targets found" in text


def test_legacy_alias_still_works():
    assert "Targets (2)" in output("list_targets")


# ---------------- target observations ----------------


class FakeRecord:
    def __init__(self, component_id, source, display_key, value, observed_at=None):
        self.component_id = component_id
        self.source = source
        self.display_key = display_key
        self.value = value
        self.observed_at = observed_at or datetime(2026, 8, 12, 18, 19)
        self.protocol, self.subject_kind, self.subject_id = display_key.split(".")[:3]


RECORDS = [
    FakeRecord(None, "ip_scan", "ip.host.198.18.34.1.alive", True),
    FakeRecord("comp_tcam_001", "doip_did_enum", "uds.did.F190.response",
               {"nrc": None, "len": 17, "security": False}),
    FakeRecord("comp_vgm_001", "doip_did_enum", "uds.did.F1A0.response",
               {"nrc": "0x33", "len": 0, "security": True}),
]


class ObservationShell(TargetShell):
    def __init__(self, records=RECORDS, **kwargs):
        super().__init__(**kwargs)
        self._records = records

    def _observation_repository(self):
        records = self._records

        class Repo:
            @staticmethod
            def current(_target_id):
                return records

        return Repo()


def obs_output(command, **kwargs):
    shell = ObservationShell(**kwargs)
    shell.stdout = io.StringIO()
    shell.onecmd_plus_hooks(command)
    return cmd2.ansi.strip_style(shell.stdout.getvalue())


def test_observations_show_facts_with_component_and_source():
    text = obs_output("target observations zeekr_demo_001")

    assert "3 current facts from 2 tools" in text
    assert "uds.did.F190.response" in text
    assert "comp_tcam_001" in text and "comp_vgm_001" in text
    assert "(target)" in text  # target-level fact has no component


def test_observations_spell_null_and_booleans_unambiguously():
    """'nrc=None' would read as a Python artifact; the ECU either answered or did not."""
    text = obs_output("target observations zeekr_demo_001")

    assert "nrc=null" in text
    assert "nrc=0x33" in text
    assert "security=false" in text and "security=true" in text
    assert "None" not in text


def test_observations_default_to_the_active_target():
    assert "3 current facts" in obs_output("target observations")


def test_observations_without_a_selected_target_explain_what_to_do():
    text = obs_output("target observations", current_id=None)
    assert "current facts" not in text


def test_observations_report_an_empty_target_clearly():
    text = obs_output("target observations zeekr_demo_001", records=[])
    assert "No scan has recorded anything" in text


def test_observations_alias_still_works():
    assert "3 current facts" in obs_output("target_observations zeekr_demo_001")
