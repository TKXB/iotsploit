"""Target monitors in core: decoding, sources, and exclusive use of hardware.

Everything here runs against a scripted ``DebugAccess``; no probe is needed.
Readings must fail closed: a sample that cannot be trusted is ``unavailable``,
never ``running``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from iotsploit_core.core.monitoring import (
    MonitorContext, MonitorKind, MonitorService, SourceRegistry, TargetCatalog, load_monitor_kinds, parse_plan,
)
from iotsploit_core.core.monitoring.arch import cortex_m
from iotsploit_core.core.monitoring.sources.mcu_core import McuCoreKind, McuCoreOptions
from iotsploit_core.core.monitoring.source import MonitorPlanEntry
from iotsploit_core.domain.monitoring import normalize_serial, parse_usb_resource, usb_resource
from iotsploit_core.ports.debug_access import DebugAccess
from iotsploit_core.ports.resource_lease import ResourceBusyError

pytestmark = pytest.mark.unit

NRF52840_CPUID = 0x410FC241
CATALOG = TargetCatalog.load_default()
NRF52840 = CATALOG.get("NRF52840_XXAA")


class FakeAccess:
    """A core behind a probe: a memory map, a register file and a call log."""

    DEBUG_USB_VENDOR_IDS = (0x1366,)

    def __init__(self, memory=None, registers=None, *, halted=False):
        self.memory = {0xE000ED00: NRF52840_CPUID, **(memory or {})}
        self.registers = registers or {}
        self.halted = halted
        self.reads: list[int] = []
        self.calls: list = []

    def debug_architectures(self):
        return frozenset({"cortex_m"})

    def attach(self, serial, target, *, interface="swd"):
        self.calls.append(("attach", serial, target, interface))

    def detach(self):
        self.calls.append(("detach",))

    def read_mem32(self, address, count=1):
        self.reads.append(address)
        return [self.memory.get(address + 4 * index, 0) for index in range(count)]

    def read_registers(self, names):
        return [self.registers[name] for name in names]

    def halt(self):
        self.calls.append(("halt",))
        self.halted = True

    def is_halted(self):
        return self.halted

    def resume(self):
        self.calls.append(("resume",))
        self.halted = False

    def reset_core(self, *, halt=False):
        self.calls.append(("reset", halt))


def sample(memory, profile=NRF52840):
    access = FakeAccess(memory)
    return cortex_m.sample(access, profile, core="main"), access


# --- resource keys --------------------------------------------------------------------

# Shared with ui/rust/src/api/probe_lock.rs: both runtimes must derive the same key.
KEY_VECTORS = [
    (0x1366, "001050298903", "debug", "usb:1366-1050298903/debug"),
    (0x1366, "1050298903", "debug", "usb:1366-1050298903/debug"),
    (0x0403, "A50285BI", "vcom", "usb:0403-A50285BI/vcom"),
    (0x0483, "0670FF", "debug", "usb:0483-0670FF/debug"),
]


@pytest.mark.parametrize("vendor, serial, function, key", KEY_VECTORS)
def test_resource_keys_have_one_spelling_per_probe(vendor, serial, function, key):
    assert usb_resource(vendor, serial, function) == key
    assert parse_usb_resource(key) == (vendor, normalize_serial(serial), function)


@pytest.mark.parametrize("bad", ["serial:/dev/ttyACM0", "usb:zz-1/debug", "usb:1366/debug", "usb:1366-1"])
def test_malformed_resource_keys_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_usb_resource(bad)


# --- target catalog -------------------------------------------------------------------

def test_catalog_holds_the_targets_as_data():
    assert CATALOG.names() == ["NRF52840_XXAA", "NRF5340_XXAA_APP", "STM32F407VG"]
    assert NRF52840.vendor_registers == {"resetreas": 0x40000400}
    assert CATALOG.get("NRF5340_XXAA_APP").cores[0].name == "app"
    assert CATALOG.get("STM32F407VG").vendor_registers == {"rcc_csr": 0x40023874}
    with pytest.raises(ValueError, match="not supported"):
        CATALOG.get("STM32H743ZI")


# --- Cortex-M decoding ----------------------------------------------------------------

@pytest.mark.parametrize("dhcsr,state", [(1 << 24, "running"), (1 << 18, "sleeping"),
                                         (1 << 19, "lockup"), (1 << 17, "halted"),
                                         (1 << 25, "reset")])
def test_core_register_classification(dhcsr, state):
    detail, access = sample({cortex_m.DHCSR: dhcsr})

    assert detail["state"] == state
    assert access.reads.count(cortex_m.DHCSR) == 1  # read-to-clear: exactly once
    assert (detail["cause"] is None) is (state in ("running", "sleeping"))
    assert detail["sample_ended"] >= detail["sample_started"]


def test_sampling_never_halts_or_resets_the_core():
    _, access = sample({cortex_m.DHCSR: 1 << 24})
    assert access.calls == []


def test_core_halted_inside_hardfault_is_a_fault_not_a_debug_halt():
    # Measured on an nRF52840 whose locked-up core J-Link halted on connect.
    detail, _ = sample({cortex_m.DHCSR: 0x00030003, cortex_m.ICSR: 0x803,
                        cortex_m.CFSR: 0x1001, cortex_m.HFSR: 0x40000000})

    assert detail["state"] == "fault"
    assert "instruction access violation" in detail["cause"]


def test_handled_fault_bits_without_active_handler_are_evidence_only():
    detail, _ = sample({cortex_m.DHCSR: 1 << 24, cortex_m.CFSR: 1 << 25})

    assert detail["state"] == "running"
    assert detail["cause"] is None
    assert detail["fault_causes"] == ["divide by zero"]


def test_invalid_cpuid_is_unavailable_not_running():
    detail, _ = sample({0xE000ED00: 0x23000000})

    assert detail["state"] == "unavailable"
    assert "CPUID" in detail["cause"]


def test_short_read_keeps_partial_evidence():
    access = FakeAccess()
    access.read_mem32 = lambda address, count=1: [NRF52840_CPUID] if address == 0xE000ED00 else []

    detail = cortex_m.sample(access, NRF52840, core="main")

    assert detail["state"] == "unavailable"
    assert detail["registers"] == {"cpuid": NRF52840_CPUID}
    assert "Incomplete dhcsr" in detail["cause"]


def test_nrf5340_reads_its_own_reset_reason_register():
    profile = CATALOG.get("NRF5340_XXAA_APP")
    access = FakeAccess({0xE000ED00: 0x410FD213, cortex_m.DHCSR: 1 << 24})

    detail = cortex_m.sample(access, profile, core="app")

    assert detail["state"] == "running"
    assert 0x40005400 in access.reads


def test_fault_status_is_decoded_without_discarding_raw_registers():
    detail, _ = sample({cortex_m.DHCSR: 1 << 24, cortex_m.ICSR: 3,
                        cortex_m.CFSR: (1 << 9) | (1 << 15), cortex_m.HFSR: 1 << 30,
                        cortex_m.BFAR: 0x20001234})

    assert detail["fault_causes"] == ["precise data bus error", "escalated configurable fault"]
    assert detail["registers"]["bfar"] == 0x20001234
    assert "precise data bus error" in detail["cause"]


# 0xFFFFFFED: floating-point extended frame; R0-xPSR still sit at the stack pointer.
@pytest.mark.parametrize("exc_return", [0xFFFFFFFD, 0xFFFFFFED])
def test_fault_snapshot_captures_stacked_exception_context(exc_return):
    registers = dict.fromkeys(cortex_m.SNAPSHOT_REGISTERS, 0)
    registers.update({"lr": exc_return, "xpsr": 3, "psp": 0x20000100})
    frame = [1, 2, 3, 4, 12, 0x08000111, 0x08000222, 0x21000000]
    access = FakeAccess({0x20000100 + 4 * index: word for index, word in enumerate(frame)}, registers)

    snapshot = cortex_m.fault_snapshot(access, NRF52840)

    assert ("halt",) in access.calls
    assert snapshot["stack"]["pc"] == 0x08000222
    assert snapshot["stack"]["lr"] == 0x08000111
    assert snapshot["stack"]["pointer"] == 0x20000100


def test_fault_snapshot_refuses_a_stack_outside_ram():
    registers = dict.fromkeys(cortex_m.SNAPSHOT_REGISTERS, 0)
    registers.update({"lr": 0xFFFFFFF9, "xpsr": 3, "msp": 0x10000000})

    snapshot = cortex_m.fault_snapshot(FakeAccess({}, registers), NRF52840)

    assert "outside target RAM" in snapshot["stack_error"]


# --- the mcu_core source --------------------------------------------------------------

def entry(**overrides):
    values = {"kind": "mcu_core", "name": "mcu_core:main", "resource": "usb:1366-1050298903/debug",
              "target": "NRF52840_XXAA"}
    values.update(overrides)
    return parse_plan([values])[0]


def mcu_core(*backends):
    return McuCoreKind(MonitorContext(lambda: {f"drv_{i}": b for i, b in enumerate(backends)}), CATALOG)


def open_source(access, **options):
    source = mcu_core(type(access)).create(entry(options=options))
    source._backend_class = lambda: access
    source.open()
    return source


def test_fake_backend_satisfies_the_debug_access_port():
    assert issubclass(FakeAccess, DebugAccess)


def test_source_attaches_by_serial_and_reports_an_envelope():
    access = FakeAccess({cortex_m.DHCSR: 1 << 24})
    source = open_source(access)

    observation = source.end()
    source.close()

    assert access.calls[0] == ("attach", "1050298903", "NRF52840_XXAA", "swd")
    assert access.calls[-1] == ("detach",)
    assert observation["kind"] == "mcu_core" and observation["health"] == "ok"
    assert observation["resource"] == "usb:1366-1050298903/debug"
    assert observation["window"][0] == observation["window"][1] == observation["observed_at"]
    assert observation["detail"]["core"] == "main"


def test_unhealthy_sample_carries_its_cause_as_a_reason():
    observation = open_source(FakeAccess({cortex_m.DHCSR: 1 << 19})).end()

    assert observation["health"] == "fault"
    assert observation["reasons"] == ["CPU lockup"]


def test_recovery_resets_without_halting_and_needs_two_healthy_samples():
    access = FakeAccess({cortex_m.DHCSR: 1 << 24})
    source = open_source(access, boot_timeout_ms=100)
    samples = iter([{"health": "reset"}, {"health": "ok", "n": 1}, {"health": "ok", "n": 2}])
    source.end = lambda: next(samples)

    result = source.recover(expected=False)

    assert ("reset", False) in access.calls
    assert result["recovered"] is True and result["baseline"]["n"] == 2


def test_expected_reset_only_resumes_a_stopped_core():
    access = FakeAccess({cortex_m.DHCSR: 1 << 24}, halted=True)
    source = open_source(access, boot_timeout_ms=100)

    result = source.recover(expected=True)

    assert ("resume",) in access.calls and not any(call[0] == "reset" for call in access.calls)
    assert result["recovered"] is True and result["reset"] is False


def test_recovery_gives_up_at_the_deadline():
    source = open_source(FakeAccess({cortex_m.DHCSR: 1 << 19}), boot_timeout_ms=100)

    result = source.recover(expected=False)

    assert result["recovered"] is False
    assert result["last_observation"]["detail"]["state"] == "lockup"


@pytest.mark.parametrize("overrides, message", [
    ({"resource": "usb:1366-1050298903/vcom"}, "debug function"),
    ({"resource": "usb:0483-0670FF/debug"}, "No debug backend drives USB vendor 0x0483"),
    ({"target": "STM32H743ZI"}, "not supported"),
    ({"options": {"recovery_policy": "pray"}}, "recovery_policy is invalid"),
    ({"options": {"expected_reset_prefixes": ["zz"]}}, "hexadecimal"),
    ({"options": {"expected_reset_prefixes": [""]}}, "empty prefix"),
    ({"options": {"boot_timeout_ms": 50}}, "boot_timeout_ms"),
    ({"options": {"settle_ms": "20"}}, "settle_ms"),
    ({"options": {"max_recoveries": 101}}, "max_recoveries"),
    ({"options": {"core": "net"}}, "no core 'net'"),
])
def test_invalid_entries_are_rejected_before_any_hardware(overrides, message):
    with pytest.raises(ValueError, match=message):
        mcu_core(FakeAccess).validate(entry(**overrides))


def test_options_default_to_the_first_core_and_legacy_limits():
    options = McuCoreOptions.parse({}, NRF52840)
    assert (options.core, options.settle_ms, options.boot_timeout_ms, options.max_recoveries) == ("main", 20, 5000, 3)


def test_backend_without_the_target_architecture_is_refused():
    class RiscvOnly(FakeAccess):
        def debug_architectures(self):
            return frozenset({"riscv"})

    access = RiscvOnly()
    source = mcu_core(RiscvOnly).create(entry())
    source._backend_class = lambda: access
    with pytest.raises(ValueError, match="cannot reach cortex_m"):
        source.open()


def test_mcu_core_offers_probes_from_every_debug_backend_and_the_catalog_targets():
    class StLink(FakeAccess):
        def scan(self):
            return [SimpleNamespace(name="STM32 STLink (57FF)")]

        def resource_key(self, device):
            return "usb:0483-57FF/debug"

    class MissingSdk(FakeAccess):
        def scan(self):
            raise RuntimeError("SDK not installed")

    kind = McuCoreKind(MonitorContext(lambda: {"drv_stlink": StLink, "drv_jlink": MissingSdk, "drv_can": object}),
                       CATALOG)
    described = kind.describe()

    assert described["parameters"]["resource"]["validation"]["choices"] == [
        {"value": "usb:0483-57FF/debug", "label": "STM32 STLink (57FF)"}]
    assert described["parameters"]["target"]["validation"]["choices"] == CATALOG.names()
    assert described["display"] == {"registers": "hex"}


def test_kinds_load_from_plugin_files_and_a_broken_file_is_skipped(tmp_path):
    (tmp_path / "beat.py").write_text(
        "from iotsploit_core.core.monitoring import MonitorKind\n\n"
        "class Beat(MonitorKind):\n    KIND = 'beat'\n")
    (tmp_path / "broken.py").write_text("raise ImportError('vendor SDK missing')\n")

    kinds = {kind.KIND: kind for kind in load_monitor_kinds(MonitorContext(dict), tmp_path)}

    assert kinds["beat"].describe() == {"kind": "beat", "name": "beat", "description": "",
                                        "parameters": {}, "display": {}}


# --- plans, service, leases -----------------------------------------------------------

class MemoryLease:
    def __init__(self):
        self.held: dict[str, str] = {}
        self.log: list = []

    def acquire(self, resource, owner):
        if resource in self.held:
            raise ResourceBusyError(resource, self.held[resource])
        self.held[resource] = owner
        self.log.append(("acquire", resource))

    def release(self, resource, owner):
        if self.held.get(resource) == owner:
            del self.held[resource]
            self.log.append(("release", resource))


class StubSource:
    def __init__(self, plan_entry, log, fail_open=False):
        self.entry, self.settle_ms, self.log, self.fail_open = plan_entry, 0, log, fail_open

    def open(self):
        self.log.append(("open", self.entry.name))
        if self.fail_open:
            raise RuntimeError("probe unplugged")

    def begin(self):
        self.log.append(("begin", self.entry.name))

    def end(self):
        self.log.append(("end", self.entry.name))
        return {"monitor": self.entry.name}

    def recover(self, expected):
        return {"recovered": True}

    def close(self):
        self.log.append(("close", self.entry.name))


class StubKind(MonitorKind):
    KIND = "stub"

    def __init__(self, log, failing=()):
        super().__init__(MonitorContext(dict))
        self.log, self.failing = log, failing

    def create(self, entry):
        return StubSource(entry, self.log, fail_open=entry.name in self.failing)


def stub_service(lease, log, failing=()):
    registry = SourceRegistry()
    registry.register(StubKind(log, failing))
    return MonitorService(registry, lease)


def stub_plan(*names):
    return [MonitorPlanEntry(kind="stub", name=name, resource=f"stub:{name}") for name in names]


def test_a_failed_open_releases_everything_already_held():
    lease, log = MemoryLease(), []
    service = stub_service(lease, log, failing={"b"})

    with pytest.raises(RuntimeError, match="unplugged"):
        service.open(stub_plan("a", "b"), owner="campaign 1")

    assert lease.held == {}
    assert ("close", "a") in log and ("close", "b") in log


def test_a_busy_resource_is_refused_with_its_holder_and_nothing_opens():
    lease, log = MemoryLease(), []
    service = stub_service(lease, log)
    held = service.open(stub_plan("a"), owner="campaign 1")

    with pytest.raises(ResourceBusyError, match="campaign 1"):
        service.open(stub_plan("a"), owner="manual check")
    held.close()
    service.check(stub_plan("a")[0], owner="manual check")

    assert lease.held == {}
    assert log.count(("open", "a")) == 2


def test_manual_check_is_one_window_and_always_closes():
    lease, log = MemoryLease(), []

    assert stub_service(lease, log).check(stub_plan("a")[0], owner="check") == {"monitor": "a"}
    assert log == [("open", "a"), ("begin", "a"), ("end", "a"), ("close", "a")]


@pytest.mark.parametrize("raw, message", [
    ("nope", "must be a list"),
    ([{"kind": "stub"}], "resource is required"),
    ([{"kind": "stub", "name": "x", "resource": "r1"}, {"kind": "stub", "name": "x", "resource": "r2"}], "unique"),
    ([{"kind": "stub", "resource": "r"}, {"kind": "stub", "resource": "r"}], "only one monitor"),
    ([{"kind": "uart", "resource": "serial:x"}], "Unknown monitor kind"),
])
def test_plans_are_validated_before_hardware(raw, message):
    with pytest.raises(ValueError, match=message):
        stub_service(MemoryLease(), []).plan(raw)
