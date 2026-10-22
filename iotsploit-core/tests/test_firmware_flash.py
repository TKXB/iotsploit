"""FirmwareToolService.flash is the one place flash options are merged.

The web UI, the CLI and three device drivers used to merge manifest options
and pick defaults each on their own, and the copies drifted: the same ESP32
entry flashed at the manifest's flash size from a driver but at a hardcoded
2MB from the web view. Every caller now goes through ``flash``. These tests pin
the merge order (manifest, then the caller's overrides) and the defaults, so a
change to either shows up here rather than on a bricked board.
"""

from __future__ import annotations

import pytest

from iotsploit_core.core.tool_service import FirmwareToolService

pytestmark = pytest.mark.unit


class RecordingProgrammer:
    """Stands in for a programmer: records each call instead of running a tool."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, method):
        def record(**kwargs):
            self.calls.append((method, kwargs))
            return "result"
        return record


def make_service(manifests):
    # Skip __init__: it probes the host for esptool and friends and writes
    # under the real home directory. flash() needs only these attributes.
    service = FirmwareToolService.__new__(FirmwareToolService)
    service.manifests = manifests
    for name in ("esp32", "stm32", "dfu", "fpga", "greatfet"):
        setattr(service, name, RecordingProgrammer())
    return service


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "app.bin"
    path.write_bytes(b"\x00")
    return str(path)


def test_esp32_multi_file_flash_uses_the_manifest_flash_geometry(image):
    service = make_service({"wifi_tool": {
        "device_type": "esp32",
        "flash_options": {
            "chip": "esp32s3", "flash_mode": "qio", "flash_freq": "40m", "flash_size": "8MB",
            "files": [{"address": "0x10000", "path": image}],
        },
    }})

    result = service.flash("wifi_tool", {"port": "/dev/ttyACM0"})

    assert result == "result"
    assert service.esp32.calls == [("flash_multi", {
        "port": "/dev/ttyACM0", "chip": "esp32s3", "baud": "460800",
        "files": [{"address": "0x10000", "path": image}],
        "flash_mode": "qio", "flash_freq": "40m", "flash_size": "8MB",
    })]


def test_caller_overrides_win_over_manifest_options(image):
    service = make_service({"app": {
        "path": image,
        "device_type": "esp32",
        "flash_options": {"port": "/dev/ttyACM2", "baud": "115200", "address": "0x0"},
    }})

    service.flash("app", {"port": "/dev/ttyUSB1"})

    assert service.esp32.calls == [("flash_single", {
        "port": "/dev/ttyUSB1", "chip": "esp32s3", "baud": "115200",
        "firmware_path": image, "address": "0x0",
    })]


def test_esp32_flash_without_a_port_is_refused_before_running_esptool(image):
    service = make_service({"app": {"path": image, "device_type": "esp32"}})

    with pytest.raises(ValueError, match="needs a serial port"):
        service.flash("app")

    assert service.esp32.calls == []


@pytest.mark.parametrize("overrides, method", [
    (None, "flash_bitstream"),
    ({"target": "sram"}, "load_sram"),
    ({"target": "flash"}, "flash_bitstream"),
])
def test_fpga_target_picks_sram_or_configuration_flash(image, overrides, method):
    service = make_service({"func": {
        "path": image, "device_type": "fpga", "flash_options": {"cable": "ft2232_b"},
    }})

    service.flash("func", overrides)

    assert [call[0] for call in service.fpga.calls] == [method]
    assert service.fpga.calls[0][1]["cable"] == "ft2232_b"


def test_unregistered_firmware_raises_key_error():
    service = make_service({})

    with pytest.raises(KeyError, match="not_there"):
        service.flash("not_there")


def test_unsupported_device_type_raises_value_error(image):
    service = make_service({"ble": {"path": image, "device_type": "nrf52"}})

    with pytest.raises(ValueError, match="nrf52"):
        service.flash("ble")
