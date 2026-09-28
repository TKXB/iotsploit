"""Invalid debug reads must fail closed; reads must never halt/reset the MCU."""
from types import SimpleNamespace

import pytest

from iotsploit_drivers.jlink.drv_jlink import JLinkAbility

pytestmark = pytest.mark.unit


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
