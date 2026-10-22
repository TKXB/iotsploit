"""ST-LINK as a probe driver and as a plain DebugAccess transport.

Decoding what the registers mean is tested in iotsploit-core
(tests/test_target_monitoring.py); this driver only moves words.
"""
from types import SimpleNamespace

import pytest

from iotsploit_core.domain.device import DeviceType
from iotsploit_core.ports.debug_access import DebugAccess
from iotsploit_drivers.stlink import drv_stlink
from iotsploit_drivers.stlink.drv_stlink import STLinkDriver

pytestmark = pytest.mark.unit

SERIAL = "57FF6C064967485623601087"


def test_scan_classifies_stlink_probe_as_usb(monkeypatch):
    probe = SimpleNamespace(unique_id=SERIAL, product_name="STM32 STLink")
    monkeypatch.setattr(drv_stlink.StlinkProbe, "get_all_connected_probes", lambda: [probe])

    [device] = STLinkDriver()._scan_impl()

    assert device.device_type is DeviceType.USB
    assert device.name == f"STM32 STLink ({SERIAL})"
    assert device.attributes["probe_sn"] == SERIAL


def test_stlink_is_a_debug_access_backend_for_st_probes():
    assert issubclass(STLinkDriver, DebugAccess)
    assert STLinkDriver.DEBUG_USB_VENDOR_IDS == (0x0483,)
    assert STLinkDriver().debug_architectures() == frozenset({"cortex_m"})


def test_resource_key_matches_the_usb_serial_spelling():
    driver = STLinkDriver()
    assert driver.resource_key(SimpleNamespace(attributes={"probe_sn": SERIAL})) == f"usb:0483-{SERIAL}/debug"
    assert driver.resource_key(SimpleNamespace(attributes={})) is None


def test_initialize_without_target_never_opens_the_probe(monkeypatch):
    monkeypatch.setattr(drv_stlink.StlinkProbe, "get_probe_with_id", lambda serial: pytest.fail("probe opened"))
    device = SimpleNamespace(name="ST-LINK", attributes={"probe_sn": SERIAL})

    with pytest.raises(ValueError, match="explicit target_device"):
        STLinkDriver()._initialize_impl(device)


def test_attach_opens_a_generic_cortex_m_session_without_halting(monkeypatch):
    opened, closed = [], []

    class FakeSession:
        def __init__(self, probe, **options):
            opened.append((probe, options))

        def open(self):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr(drv_stlink.StlinkProbe, "get_probe_with_id", lambda serial: f"probe {serial}")
    monkeypatch.setattr(drv_stlink, "Session", FakeSession)
    driver = STLinkDriver()

    driver.attach(SERIAL, "STM32F407VG", interface="swd")
    driver.detach()
    driver.detach()

    assert opened == [(f"probe {SERIAL}",
                       {"target_override": "cortex_m", "connect_mode": "attach", "dap_protocol": "swd"})]
    assert closed == [True] and driver.session is None


def test_failed_open_releases_the_probe(monkeypatch):
    closed = []

    class FailingSession:
        def __init__(self, probe, **options):
            pass

        def open(self):
            raise RuntimeError("STLink is using an unsupported, older firmware version")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(drv_stlink.StlinkProbe, "get_probe_with_id", lambda serial: object())
    monkeypatch.setattr(drv_stlink, "Session", FailingSession)
    driver = STLinkDriver()

    with pytest.raises(RuntimeError, match="older firmware"):
        driver.attach(SERIAL, "STM32F407VG")
    assert closed == [True] and driver.session is None


def test_transport_calls_never_halt_on_their_own():
    calls = []
    target = SimpleNamespace(
        read_memory_block32=lambda address, count: calls.append(("read", address, count)) or [7] * count,
        read_core_registers_raw=lambda names: calls.append(("regs", names)) or [0] * len(names),
        reset=lambda: calls.append(("reset",)),
        get_state=lambda: drv_stlink.Target.State.HALTED,
        resume=lambda: calls.append(("resume",)),
    )
    driver = STLinkDriver()
    driver.session = SimpleNamespace(board=SimpleNamespace(target=target))

    assert driver.read_mem32(0xE000EDF0) == [7]
    assert driver.read_registers(("pc", "sp")) == [0, 0]
    driver.reset_core()
    assert driver.is_halted() is True
    driver.resume()

    assert calls == [("read", 0xE000EDF0, 1), ("regs", ["pc", "sp"]), ("reset",), ("resume",)]


def test_transport_needs_an_open_probe():
    with pytest.raises(RuntimeError, match="not initialized"):
        STLinkDriver().read_mem32(0)
