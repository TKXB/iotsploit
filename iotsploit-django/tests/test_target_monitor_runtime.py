"""A monitored campaign end to end, and the wire format older clients still read.

The payloads in ``fixtures/monitor_legacy/rig_nrf52840.json`` were captured
from the J-Link rig before monitors were generalised. The Flutter build of that
time reads the flat ``core_observation`` dict, and target history stores it, so
its keys are pinned here against the real thing rather than against a copy of
the code that produces them.

Hardware is replaced at the two edges only: the probe (a scripted
``DebugAccess``) and the UART port. The monitor service, sources, policies,
harness, runtime, recorder and file lease are the real ones.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_core.core.monitoring import TargetCatalog, parse_plan  # noqa: E402
from iotsploit_core.core.monitoring.arch import cortex_m  # noqa: E402
from iotsploit_core.core.device_manager import DeviceDriverManager  # noqa: E402
from iotsploit_core.domain.observation import StartedScan  # noqa: E402
from iotsploit_core.ports.resource_lease import ResourceBusyError  # noqa: E402
from iotsploit_django.adapters.filelock.resource_lease import FileResourceLease, lock_file_name  # noqa: E402
from iotsploit_django.composition_root import core_container  # noqa: E402
from iotsploit_django.tools import monitor_compat  # noqa: E402
from iotsploit_django.tools.iot_protocol_runtime import OrchestratorAdapter  # noqa: E402

pytestmark = [pytest.mark.django, pytest.mark.integration]

RIG = json.loads((Path(__file__).parent / "fixtures" / "monitor_legacy" / "rig_nrf52840.json").read_text())
RUNNING = 0x01010001  # DHCSR as read on the rig: S_RETIRE_ST, S_REGRDY, C_DEBUGEN
LOCKUP = 0x00080001


class ScriptedProbe:
    """An nRF52840 behind a J-Link whose DHCSR follows a script, then stays put."""

    DEBUG_USB_VENDOR_IDS = (0x1366,)
    script: list[int] = []
    attached: list = []
    detached: list = []

    def debug_architectures(self):
        return frozenset({"cortex_m"})

    def attach(self, serial, target, *, interface="swd"):
        ScriptedProbe.attached.append((serial, target))

    def detach(self):
        ScriptedProbe.detached.append(True)

    def read_mem32(self, address, count=1):
        if address == cortex_m.DHCSR:
            value = ScriptedProbe.script.pop(0) if len(ScriptedProbe.script) > 1 else ScriptedProbe.script[0]
            return [value]
        return [{cortex_m.CPUID: 0x410FC241, 0x40000400: 1}.get(address, 0)]

    def read_registers(self, names):
        return [0] * len(names)

    def halt(self):
        pass

    def is_halted(self):
        return False

    def resume(self):
        pass

    def reset_core(self, *, halt=False):
        pass


class SilentUart:
    def __init__(self, device, baudrate=115200, timeout=0.1):
        self.sent = []

    def send(self, data):
        self.sent.append(data)

    def receive(self, timeout=0.1):
        return None

    def close(self):
        pass


class RecordingSink:
    instances: list = []

    def __init__(self):
        self.started, self.completed, self.failed = None, [], []
        RecordingSink.instances.append(self)

    def start_scans(self, **kwargs):
        self.started = kwargs
        return [StartedScan(scan_id="scan-1", scope=kwargs["scopes"][0])]

    def complete_scan(self, scan_id, facts, *, is_complete=True):
        self.completed.append(facts)

    def fail_scan(self, scan_id, error):
        self.failed.append(error)


class DriverClasses:
    def driver_classes(self):
        return {"drv_jlink": ScriptedProbe}


@pytest.fixture
def lease(tmp_path):
    return FileResourceLease(tmp_path / "locks")


@pytest.fixture
def campaign(monkeypatch, lease):
    """Run a legacy ``core_monitor`` campaign over three payloads; return what it emitted."""
    from iotsploit_django.composition_root import wiring
    from iotsploit_django.adapters.django import observation_repository
    from iotsploit_django.tools import iot_fuzzer_bridge, iot_fuzzer_manager
    from iotsploit_fuzzer.interfaces import uart_interface

    events, states = [], []
    service = core_container.build_monitor_service(DriverClasses(), lease, catalog=TargetCatalog.load_default())
    monkeypatch.setattr(wiring, "get_monitor_service", lambda: service)
    monkeypatch.setattr(uart_interface, "UARTInterface", SilentUart)
    monkeypatch.setattr(observation_repository, "ObservationRepository", RecordingSink)
    monkeypatch.setattr(iot_fuzzer_bridge.IoTFuzzerBridge, "get_instance",
                        staticmethod(lambda: SimpleNamespace(emit_event=lambda kind, data: events.append((kind, data)))))
    monkeypatch.setattr(iot_fuzzer_manager.IoTFuzzerManager, "get_instance",
                        staticmethod(lambda: SimpleNamespace(update_campaign_state=lambda cid, u: states.append(u))))
    ScriptedProbe.attached, ScriptedProbe.detached = [], []
    RecordingSink.instances = []

    def run(script, **core_monitor):
        ScriptedProbe.script = list(script)
        engine = SimpleNamespace(generate_mutations=lambda sources, iterations: {
            "fixed": [SimpleNamespace(mutated_data=p) for p in (b"\x22\xf1\x90", b"hello\n", b"\x3e\x00")]})
        adapter = OrchestratorAdapter({
            "campaign_id": "rig-replay",
            "fuzzing_engine": engine,
            "test_cases": [{"id": 1, "name": "fixed", "protocol_type": "uart", "frame_fields": [], "iterations": 1}],
            "protocol_config": {"protocol_type": "uart", "port": "/dev/ttyACM0", "timeout": 200},
            "delay": 0,
            "core_monitor": {"probe_serial": "1050298903", "target_device": "NRF52840_XXAA",
                             "settle_ms": 0, "target_id": "target-1", **core_monitor},
        }, True)
        adapter.start()
        adapter.fuzzer_thread.join(timeout=10)
        return adapter

    return SimpleNamespace(run=run, events=events, states=states)


def core_events(events):
    return [data for kind, data in events if "core_observation" in data]


def test_healthy_campaign_emits_what_the_rig_emitted(campaign, lease):
    adapter = campaign.run([RUNNING])

    assert adapter.failure is None
    observed = core_events(campaign.events)
    assert len(observed) == 4  # preflight + one per case, as on the rig
    preflight, case = observed[0]["core_observation"], observed[1]["core_observation"]
    assert set(preflight) == set(RIG["preflight_event"]["core_observation"])
    assert set(case) == set(RIG["case_event"]["core_observation"])
    assert set(case["before"]) == set(RIG["case_event"]["core_observation"]["before"])
    assert case["state"] == "running" and case["registers"]["resetreas"] == 1
    assert set(campaign.states[1]) == {"core_observation", "monitor_verdicts"}
    # The probe is attached once, released at the end, and its lease with it.
    assert ScriptedProbe.attached == [("1050298903", "NRF52840_XXAA")]
    assert ScriptedProbe.detached == [True]
    lease.acquire("usb:1366-1050298903/debug", "next user")


def test_crash_stops_the_campaign_and_closes_target_history(campaign):
    campaign.run([RUNNING, RUNNING, LOCKUP])

    stopped = [data for kind, data in campaign.events if data.get("event_type") == "campaign_stopped"]
    assert stopped and stopped[-1]["reason"] == "CPU lockup"
    crash = core_events(campaign.events)[-1]["core_observation"]
    assert crash["crashed"] is True and crash["detected_reason"] == "CPU lockup"
    sink = RecordingSink.instances[0]
    assert sink.started["scopes"][0].scope_key == "jtag-core:NRF52840_XXAA:1050298903"
    [fact] = sink.completed[0]
    assert fact.value["state"] == "lockup"


def test_a_held_probe_refuses_the_campaign(campaign, lease):
    lease.acquire("usb:1366-1050298903/debug", "boundary scan")

    with pytest.raises(ResourceBusyError, match="boundary scan"):
        campaign.run([RUNNING])
    assert ScriptedProbe.attached == []


def test_failed_preflight_releases_the_probe(campaign, lease):
    with pytest.raises(RuntimeError, match="MCU preflight failed: CPU lockup"):
        campaign.run([LOCKUP])
    lease.acquire("usb:1366-1050298903/debug", "next user")


# --- legacy translation ---------------------------------------------------------------

def test_flattened_sample_has_the_rig_check_keys():
    rig = RIG["check_response"]["monitor"]["observation"]
    envelope = {
        "monitor": "mcu_core", "kind": "mcu_core", "resource": "usb:1366-1050298903/debug",
        "target": rig["target"], "window": (1.0, 1.0), "observed_at": rig["observed_at"],
        "health": "ok", "reasons": [],
        "detail": {"core": "main", "state": rig["state"], "cause": None, "fault_causes": [],
                   "active_exception": 0, "retired": True, "reset_observed": False,
                   "registers": rig["registers"], "arch": "cortex_m",
                   "sample_started": rig["sample_started"], "sample_ended": rig["sample_ended"]},
    }

    assert monitor_compat.flatten_mcu_core(envelope) == rig


@pytest.mark.parametrize("config, message", [
    ("nope", "must be an object"),
    ({"probe_serial": "0", "target_device": "NRF52840_XXAA"}, "probe serial is required"),
    ({"probe_serial": "12", "settle_ms": "soon"}, "settle_ms must be an integer"),
])
def test_legacy_config_errors_keep_their_messages(config, message):
    with pytest.raises(ValueError, match=message):
        monitor_compat.legacy_plan(config)


def test_legacy_config_becomes_a_one_entry_plan():
    [entry] = parse_plan(monitor_compat.legacy_plan({
        "probe_serial": "1050298903", "target_device": "NRF5340_XXAA_APP", "settle_ms": "30",
        "recovery_policy": "reset_continue", "expected_reset_prefixes": ["1101"], "target_id": " t1 ",
    }))

    assert (entry.kind, entry.name, entry.target, entry.target_id) == ("mcu_core", "mcu_core", "NRF5340_XXAA_APP", "t1")
    assert entry.resource == "usb:1366-1050298903/debug"
    assert entry.options["settle_ms"] == 30 and entry.options["expected_reset_prefixes"] == ["1101"]


def test_legacy_config_names_a_non_segger_probe_by_vendor():
    [entry] = monitor_compat.legacy_plan({"probe_serial": "57FF6C064967485623601087",
                                          "probe_vendor_id": 0x0483, "target_device": "STM32F407VG"})

    assert entry["resource"] == "usb:0483-57FF6C064967485623601087/debug"


# --- composition root -----------------------------------------------------------------

def test_container_resolves_the_real_jlink_driver_for_segger_probes(lease):
    from iotsploit_drivers.jlink.drv_jlink import JLinkAbility

    manager = SimpleNamespace(driver_classes=lambda: {"drv_socketcan": object, "drv_jlink": JLinkAbility})
    service = core_container.build_monitor_service(manager, lease)
    [entry] = service.plan(monitor_compat.legacy_plan({"probe_serial": "1050298903",
                                                      "target_device": "NRF52840_XXAA"}))

    assert service.kinds() == ["mcu_core"]
    assert entry.resource == "usb:1366-1050298903/debug"
    assert DeviceDriverManager.driver_capabilities(JLinkAbility) == ["debug_access"]
    assert isinstance(core_container.build_resource_lease(), FileResourceLease)


def test_container_resolves_the_real_stlink_driver_for_st_probes(lease):
    from iotsploit_drivers.stlink.drv_stlink import STLinkDriver

    manager = SimpleNamespace(driver_classes=lambda: {"drv_jlink": object, "drv_stlink": STLinkDriver})
    service = core_container.build_monitor_service(manager, lease)
    [entry] = service.plan(monitor_compat.legacy_plan({"probe_serial": "57FF6C064967485623601087",
                                                      "probe_vendor_id": 0x0483,
                                                      "target_device": "STM32F407VG"}))

    assert entry.resource == "usb:0483-57FF6C064967485623601087/debug"
    assert DeviceDriverManager.driver_capabilities(STLinkDriver) == ["debug_access"]


# --- file lease -----------------------------------------------------------------------

def test_lock_file_names_are_flat_and_stable():
    assert lock_file_name("usb:1366-1050298903/debug") == "usb_1366-1050298903_debug.lock"


def test_lease_is_exclusive_within_a_process_and_ignores_foreign_releases(lease):
    lease.acquire("usb:1366-1/debug", "campaign 1")

    with pytest.raises(ResourceBusyError, match="campaign 1"):
        lease.acquire("usb:1366-1/debug", "manual check")
    lease.release("usb:1366-1/debug", "manual check")
    with pytest.raises(ResourceBusyError):
        lease.acquire("usb:1366-1/debug", "manual check")
    lease.release("usb:1366-1/debug", "campaign 1")
    lease.acquire("usb:1366-1/debug", "manual check")


def test_lease_is_exclusive_across_processes_and_dies_with_its_holder(tmp_path):
    lock_dir = tmp_path / "locks"
    holder = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys, time
            from iotsploit_django.adapters.filelock.resource_lease import FileResourceLease
            lease = FileResourceLease({str(lock_dir)!r}, process="iotsploit-ui")
            lease.acquire("usb:1366-1/debug", "boundary scan")
            print("held", flush=True)
            time.sleep(60)
        """)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        lease = FileResourceLease(lock_dir)
        with pytest.raises(ResourceBusyError) as refused:
            lease.acquire("usb:1366-1/debug", "campaign 1")
        assert f"boundary scan (iotsploit-ui, pid {holder.pid})" in str(refused.value)
    finally:
        holder.kill()
        holder.wait()
    lease.acquire("usb:1366-1/debug", "campaign 1")
