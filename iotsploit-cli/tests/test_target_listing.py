"""Rendering and dispatch for `target list`.

The listing is how an operator confirms which vehicle they are pointed at before
running anything against it, so the parts asserted here are the ones that cause
real mistakes when wrong: the active-target marker, and components/interfaces
being visible at all.
"""

import io

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
            },
            {
                "component_id": "comp_vgm_001", "name": "VGM", "type": "ecu", "status": "inactive",
                "properties": {"doip_logical_address": "0x1001"},
            },
        ],
        "interfaces": [
            {"interface_id": "intf_obd_001", "name": "OBD-II", "type": "diagnostic", "status": "active",
             "properties": {"protocol": "DoIP"}},
        ],
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
        "interfaces": [],
    },
]


class FakeTargetManager:
    def __init__(self, targets, current_id=None):
        self._targets = targets
        self._current_id = current_id

    def get_all_targets(self):
        return self._targets

    def get_current_target(self):
        if self._current_id is None:
            return None
        return type("T", (), {"target_id": self._current_id})()


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
    # component/interface counts belong in the summary; the old listing omitted them
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


def test_detail_shows_components_and_interfaces():
    text = output("target list zeekr_demo_001")

    assert "Components (2)" in text
    assert "TCAM" in text and "comp_tcam_001" in text
    assert "ZK2025TCAM000001" in text  # type-specific field
    assert "ip_address=198.18.34.1" in text  # free-form property
    assert "Interfaces (1)" in text
    assert "OBD-II" in text and "protocol=DoIP" in text
    assert "model_year" in text


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
