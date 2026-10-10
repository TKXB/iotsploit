"""The firmware registry reports only what is true on disk.

Built-in entries come from the iotsploit-drivers package manifest, and user
entries are saved to ~/.iotsploit. Removing a built-in entry used to report
success, but the entry came back on the next start. A failed save also
reported success. Both told the user something false.
"""

from __future__ import annotations

import logging

import pytest

from iotsploit_core.core.tool_service import FirmwareToolService

pytestmark = pytest.mark.unit

BUILTIN = {"iotsploit_func": {"resource": "pkg:func.bit", "device_type": "fpga", "version": "1.0.0"}}


def make_service(tmp_path, manifests):
    # Skip __init__: it probes the host for flashing tools and writes under
    # the real home directory.
    service = FirmwareToolService.__new__(FirmwareToolService)
    service.logger = logging.getLogger("test_firmware_registry")
    service.manifests = manifests
    service.user_manifest_file = tmp_path / "firmware_manifest.json"
    service._load_builtin_manifest = lambda: BUILTIN
    return service


def test_a_built_in_entry_cannot_be_removed(tmp_path):
    service = make_service(tmp_path, dict(BUILTIN))

    removed = service.remove_firmware("iotsploit_func")

    assert removed is False
    assert "iotsploit_func" in service.manifests


def test_a_user_entry_is_removed_and_the_removal_is_saved(tmp_path):
    image = tmp_path / "mine.bin"
    image.write_bytes(b"\x00")
    service = make_service(tmp_path, dict(BUILTIN))
    service.add_firmware("mine", str(image), "esp32", "1.0.0")

    removed = service.remove_firmware("mine")

    assert removed is True
    assert service.user_manifest_file.read_text().strip() == "{}"


def test_adding_firmware_reports_failure_when_the_manifest_cannot_be_saved(tmp_path):
    image = tmp_path / "mine.bin"
    image.write_bytes(b"\x00")
    service = make_service(tmp_path, {})
    service.user_manifest_file = tmp_path / "missing_dir" / "firmware_manifest.json"

    added = service.add_firmware("mine", str(image), "esp32", "1.0.0")

    assert added is False


def test_file_sizes_lists_every_flashed_file_and_marks_missing_ones(tmp_path):
    present = tmp_path / "bootloader.bin"
    present.write_bytes(b"\x00" * 4)
    service = make_service(tmp_path, {"multi": {
        "device_type": "esp32",
        "flash_options": {"files": [
            {"address": "0x0", "path": str(present)},
            {"address": "0x10000", "path": str(tmp_path / "gone.bin")},
        ]},
    }})

    sizes = service.file_sizes("multi")

    assert sizes == [4, None]


def test_file_sizes_is_empty_for_an_entry_that_names_no_file(tmp_path):
    service = make_service(tmp_path, {"bare": {"device_type": "esp32"}})

    assert service.file_sizes("bare") == []
