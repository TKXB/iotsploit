"""Invalid debug reads must fail closed; reads must never halt/reset the MCU."""
from types import SimpleNamespace

import pytest

from iotsploit_core.domain.device import DeviceType
from iotsploit_drivers.jlink import drv_jlink
from iotsploit_drivers.jlink.drv_jlink import JLinkAbility

pytestmark = pytest.mark.unit


def test_scan_classifies_jlink_probe_as_usb(monkeypatch):
    probe = SimpleNamespace(
        connected_emulators=lambda: [SimpleNamespace(SerialNumber=1050298903)]
    )
    monkeypatch.setattr(drv_jlink.pylink, "JLink", lambda lib: probe, raising=False)
    driver = object.__new__(JLinkAbility)
    driver._sdk_available = True
    driver._jlink_lib = object()
    driver.connected_emulators = []

    devices = driver._scan_impl()

    assert devices[0].device_type is DeviceType.USB
    assert devices[0].attributes["emulator_sn"] == "1050298903"


@pytest.mark.parametrize("dhcsr,state", [(1 << 24, "running"), (1 << 18, "sleeping"),
                                         (1 << 19, "lockup"), (1 << 17, "halted"),
                                         (1 << 25, "reset")])
def test_core_register_classification(dhcsr, state):
    reads = []

    def read(address, count):
        reads.append(address)
        return [{0xE000ED00: 0x410FC241, 0xE000EDF0: dhcsr}.get(address, 0)]

    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(memory_read32=read)
    device = SimpleNamespace(attributes={"target_device": "NRF52840_XXAA", "emulator_sn": "123"})

    result = driver.core_status(device)

    assert result["state"] == state
    assert reads.count(0xE000EDF0) == 1
    assert result["crashed"] is (state == "lockup")
    assert result["sample_ended"] >= result["sample_started"]


def test_invalid_cpuid_is_unavailable_not_running():
    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(memory_read32=lambda address, count: [0x23000000])
    device = SimpleNamespace(attributes={"target_device": "NRF52840_XXAA", "emulator_sn": "123"})

    result = driver.core_status(device)

    assert result["state"] == "unavailable"
    assert "CPUID" in result["stop_reason"]
    assert not result["crashed"]


def test_short_read_keeps_partial_evidence():
    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(memory_read32=lambda address, count: [0x410FC241] if address == 0xE000ED00 else [])
    device = SimpleNamespace(attributes={"target_device": "NRF52840_XXAA", "emulator_sn": "123"})

    result = driver.core_status(device)

    assert result["state"] == "unavailable"
    assert result["registers"] == {"cpuid": 0x410FC241}
    assert "Incomplete dhcsr" in result["stop_reason"]


def test_nrf5340_uses_application_core_profile():
    reads = []

    def read(address, count):
        reads.append(address)
        return [{0xE000ED00: 0x410FD213, 0xE000EDF0: 1 << 24}.get(address, 0)]

    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(memory_read32=read)
    device = SimpleNamespace(
        attributes={"target_device": "NRF5340_XXAA_APP", "emulator_sn": "123"}
    )

    result = driver.core_status(device)

    assert result["state"] == "running"
    assert 0x40005400 in reads


def test_fault_snapshot_captures_stacked_exception_context():
    names = [f"R{index}" for index in range(16)] + ["XPSR", "MSP", "PSP", "CONTROL"]
    registers = dict.fromkeys(names, 0)
    registers.update({"R14": 0xFFFFFFFD, "XPSR": 3, "PSP": 0x20000100})
    frame = [1, 2, 3, 4, 12, 0x08000111, 0x08000222, 0x21000000]

    def read(address, count):
        if address in (0xE000ED28, 0xE000ED2C):
            return [0]
        if address == 0x20000100:
            return frame
        raise AssertionError(f"Unexpected read at 0x{address:08X}")

    probe = SimpleNamespace(
        halt=lambda: None,
        halted=lambda: True,
        register_read_multiple=lambda requested: [registers[name] for name in requested],
        memory_read32=read,
    )
    driver = object.__new__(JLinkAbility)
    driver.jlink = probe
    device = SimpleNamespace(
        attributes={"target_device": "NRF52840_XXAA", "emulator_sn": "123"}
    )

    snapshot = driver.fault_snapshot(device)

    assert snapshot["stack"]["pc"] == 0x08000222
    assert snapshot["stack"]["lr"] == 0x08000111
    assert snapshot["stack"]["pointer"] == 0x20000100


def test_fault_status_is_decoded_without_discarding_raw_registers():
    values = {
        0xE000ED00: 0x410FC241,
        0xE000EDF0: 1 << 24,
        0xE000ED04: 3,
        0xE000ED28: (1 << 9) | (1 << 15),
        0xE000ED2C: 1 << 30,
        0xE000ED38: 0x20001234,
    }
    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(memory_read32=lambda address, count: [values.get(address, 0)])
    device = SimpleNamespace(
        attributes={"target_device": "NRF52840_XXAA", "emulator_sn": "123"}
    )

    result = driver.core_status(device)

    assert result["fault_causes"] == [
        "precise data bus error",
        "escalated configurable fault",
    ]
    assert result["registers"]["bfar"] == 0x20001234
    assert "precise data bus error" in result["stop_reason"]


def test_recover_target_resets_without_halting_and_establishes_baseline():
    reset_calls = []
    samples = iter(
        [
            {"state": "reset", "stop_reason": "reset"},
            {"state": "running", "stop_reason": None, "sample": 1},
            {"state": "running", "stop_reason": None, "sample": 2},
        ]
    )
    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(reset=lambda **kwargs: reset_calls.append(kwargs))
    driver.core_status = lambda device: next(samples)

    result = driver.recover_target(SimpleNamespace(), timeout_ms=100)

    assert reset_calls == [{"halt": False}]
    assert result["recovered"] is True
    assert result["baseline"]["sample"] == 2
