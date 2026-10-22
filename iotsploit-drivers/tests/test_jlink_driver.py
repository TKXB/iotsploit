"""J-Link as a probe driver and as a plain DebugAccess transport.

Decoding what the registers mean is tested in iotsploit-core
(tests/test_target_monitoring.py); this driver only moves words.
"""
from types import SimpleNamespace

import pytest

from iotsploit_core.domain.device import DeviceType
from iotsploit_drivers.jlink import drv_jlink
from iotsploit_drivers.jlink.drv_jlink import JLinkAbility
from iotsploit_core.ports.debug_access import DebugAccess

pytestmark = pytest.mark.unit


def test_scan_classifies_jlink_probe_as_usb(monkeypatch):
    probe = SimpleNamespace(
        connected_emulators=lambda: [SimpleNamespace(
            SerialNumber=1050298903,
            acProduct=b"J-Link OB-nRF5340-NordicSemi",
        )]
    )
    monkeypatch.setattr(drv_jlink.pylink, "JLink", lambda lib: probe, raising=False)
    driver = object.__new__(JLinkAbility)
    driver._sdk_available = True
    driver._jlink_lib = object()
    driver.connected_emulators = []

    devices = driver._scan_impl()

    assert devices[0].device_type is DeviceType.USB
    assert devices[0].name == "J-Link OB-nRF5340-NordicSemi (1050298903)"
    assert devices[0].attributes["emulator_sn"] == "1050298903"
    # The product names the probe's MCU; an nRF52840-DK reports this nRF5340 probe.
    assert "target_device" not in devices[0].attributes


def test_initialize_without_target_never_opens_the_probe(monkeypatch):
    monkeypatch.setattr(drv_jlink.pylink, "JLink", lambda **kwargs: pytest.fail("probe opened"),
                        raising=False)
    driver = object.__new__(JLinkAbility)
    driver._sdk_available = True
    driver._jlink_lib = object()
    device = SimpleNamespace(name="J-Link", attributes={"emulator_sn": "1050298903"})

    with pytest.raises(ValueError, match="explicit target_device"):
        driver._initialize_impl(device)


def test_secured_target_is_reported_and_probe_released(monkeypatch):
    closed = []
    decline = object()
    monkeypatch.setattr(drv_jlink.pylink, "enums", SimpleNamespace(
        JLinkFlags=SimpleNamespace(DLG_BUTTON_NO=decline),
        JLinkInterfaces=SimpleNamespace(SWD="swd"),
    ), raising=False)

    class SecuredProbe:
        def __init__(self, lib, unsecure_hook):
            self.unsecure_hook = unsecure_hook

        def open(self, serial_no):
            pass

        def set_tif(self, interface):
            pass

        def connect(self, target):
            answer = self.unsecure_hook(b"J-Link", b"CTRL-AP indicates that the device is secured.", 0)
            assert answer is decline
            raise RuntimeError("Unspecified error.")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(drv_jlink.pylink, "JLink", SecuredProbe, raising=False)
    driver = object.__new__(JLinkAbility)
    driver._sdk_available = True
    driver._jlink_lib = object()
    device = SimpleNamespace(name="J-Link", attributes={
        "emulator_sn": "1050298903", "target_device": "NRF52840_XXAA", "interface": "swd"})

    with pytest.raises(RuntimeError, match="readback-protected"):
        driver._initialize_impl(device)
    assert closed == [True]
    assert driver.jlink is None


def attached(**probe):
    driver = object.__new__(JLinkAbility)
    driver.jlink = SimpleNamespace(**probe)
    return driver


def test_jlink_is_a_debug_access_backend_for_segger_probes():
    assert issubclass(JLinkAbility, DebugAccess)
    assert JLinkAbility.DEBUG_USB_VENDOR_IDS == (0x1366,)
    assert attached().debug_architectures() == frozenset({"cortex_m"})


def test_resource_key_matches_the_usb_serial_spelling():
    device = SimpleNamespace(attributes={"emulator_sn": "1050298903"})
    assert object.__new__(JLinkAbility).resource_key(device) == "usb:1366-1050298903/debug"
    assert object.__new__(JLinkAbility).resource_key(SimpleNamespace(attributes={})) is None


def test_canonical_register_names_become_dll_names():
    requested = []
    driver = attached(register_read_multiple=lambda names: requested.extend(names) or [0] * len(names))

    driver.read_registers(["r0", "sp", "lr", "pc", "xpsr"])

    assert requested == ["R0", "R13 (SP)", "R14", "R15 (PC)", "XPSR"]


def test_unknown_register_is_rejected_before_the_dll():
    with pytest.raises(ValueError, match="Unknown core register 'r13'"):
        attached(register_read_multiple=lambda names: pytest.fail("reached the DLL")).read_registers(["r13"])


def test_transport_calls_never_halt_on_their_own():
    calls = []
    driver = attached(memory_read32=lambda address, count: calls.append(("read", address, count)) or [7] * count,
                      reset=lambda halt: calls.append(("reset", halt)),
                      halted=lambda: True, restart=lambda: calls.append(("restart",)))

    assert driver.read_mem32(0xE000EDF0) == [7]
    driver.reset_core()
    assert driver.is_halted() is True
    driver.resume()

    assert calls == [("read", 0xE000EDF0, 1), ("reset", False), ("restart",)]


def test_attach_connects_through_initialize_and_detach_releases():
    driver = object.__new__(JLinkAbility)
    driver.jlink = None
    seen = []
    closed = []

    def initialize(device):
        seen.append(dict(device.attributes))
        driver.jlink = SimpleNamespace(close=lambda: closed.append(True))
        return True

    driver.initialize = initialize
    driver.attach("1050298903", "NRF52840_XXAA", interface="swd")
    driver.detach()
    driver.detach()

    assert seen == [{"emulator_sn": "1050298903", "target_device": "NRF52840_XXAA", "interface": "swd"}]
    assert closed == [True] and driver.jlink is None


def test_transport_needs_an_open_probe():
    driver = object.__new__(JLinkAbility)
    driver.jlink = None
    with pytest.raises(RuntimeError, match="not initialized"):
        driver.read_mem32(0)
