"""A firmware gate must detect reboots, retain replay, and refuse ambiguous devices."""
import importlib.util
import random
from pathlib import Path

import pytest

from iotsploit_fuzzer.core.fuzzing_engine import FuzzingEngine
from iotsploit_fuzzer.generators.strategy_generator import SelectedCaseGenerator
from iotsploit_fuzzer.interfaces.usbtmc_interface import USBTMCInterface

pytestmark = pytest.mark.unit
spec = importlib.util.spec_from_file_location(
    "firmware_fuzz_gate", Path(__file__).parents[2] / "tools/hardware/firmware_fuzz_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def source():
    return {"id": "identity", "name": "SCPI identity", "protocol_type": "usbtmc",
            "frame_data": b"*IDN?\n", "target_bits": "0,1,2,3,4,5,6,7",
            "frame_fields": [], "fuzzing_rules": [], "strategies": ["random_bit"], "iterations": 20}


def test_campaign_rng_is_reproducible_without_global_random_state():
    first = SelectedCaseGenerator(FuzzingEngine(rng=random.Random(47)), [source()])
    state = random.getstate()
    try:
        random.seed(99)
        second = SelectedCaseGenerator(FuzzingEngine(rng=random.Random(47)), [source()])
    finally:
        random.setstate(state)
    assert first.payloads == second.payloads
    assert first.payloads != SelectedCaseGenerator(FuzzingEngine(rng=random.Random(48)), [source()]).payloads


def test_saved_mutants_replay_exact_bytes_without_generation():
    generator = SelectedCaseGenerator(None, [source()], saved={"identity": ["000aff", "2a49444e3f0a"]})
    assert list(generator.generate([], generator.total)) == [b"\0\n\xff", b"*IDN?\n"]


def test_unknown_required_strategy_cannot_produce_a_green_campaign():
    with pytest.raises(ValueError, match="Strategy not found"):
        SelectedCaseGenerator(FuzzingEngine(), [{**source(), "strategies": ["missing"]}])


@pytest.mark.parametrize("next_token,health", [("0123456789abcdef", "ok"), ("fedcba9876543210", "fault")])
def test_boot_observer_checks_boot_continuity(monkeypatch, next_token, health):
    tokens = iter(["0123456789abcdef", next_token])
    monkeypatch.setattr(gate, "query", lambda *args: next(tokens))
    observer = gate.BootObservation(None)
    assert observer.observe()["health"] == health


def test_missing_boot_telemetry_is_not_a_pass(monkeypatch):
    monkeypatch.setattr(gate, "query", lambda *args: "")
    with pytest.raises(ValueError, match="64-bit"):
        gate.BootObservation(None)


def test_same_usb_serial_requires_a_physical_selector(monkeypatch):
    devices = [{"serial": "0001", "bus": 1, "address": address, "ports": ports}
               for address, ports in [(22, [4, 3]), (23, [4, 1, 2])]]
    monkeypatch.setattr(USBTMCInterface, "discover", lambda: devices)
    with pytest.raises(ValueError, match="matched 2"):
        USBTMCInterface.select({"serial": "0001"})
    assert USBTMCInterface.select({"serial": "0001", "bus": 1, "ports": [4, 1, 2], "address": 9}) == devices[1]


def test_saved_usb_identity_survives_address_change(monkeypatch):
    device = {"serial": "unique", "bus": 2, "address": 42, "ports": [3]}
    monkeypatch.setattr(USBTMCInterface, "discover", lambda: [device])
    assert USBTMCInterface.select({"serial": "unique", "bus": 1, "address": 9}) == device
