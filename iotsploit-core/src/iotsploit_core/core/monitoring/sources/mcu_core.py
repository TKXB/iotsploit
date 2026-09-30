"""The ``mcu_core`` monitor kind: one CPU core sampled over a debug probe."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Mapping

from iotsploit_core.core.monitoring.arch import arch_monitor
from iotsploit_core.core.monitoring.catalog import TargetCatalog
from iotsploit_core.core.monitoring.kind import MonitorContext, MonitorKind
from iotsploit_core.core.monitoring.source import MonitorPlanEntry
from iotsploit_core.domain.monitoring import MonitorObservation, mcu_core_health, parse_usb_resource
from iotsploit_core.domain.target_profile import TargetProfile
from iotsploit_core.ports.debug_access import DebugAccess, debug_usb_vendor_ids

logger = logging.getLogger(__name__)

KIND = "mcu_core"
RECOVERY_POLICIES = ("stop", "reset_continue")


@dataclass(frozen=True)
class McuCoreOptions:
    core: str
    interface: str
    settle_ms: int
    boot_timeout_ms: int
    recovery_policy: str
    max_recoveries: int
    expected_reset_prefixes: tuple[bytes, ...]

    @classmethod
    def parse(cls, options: Mapping, profile: TargetProfile) -> "McuCoreOptions":
        core = str(options.get("core") or profile.cores[0].name)
        profile.core(core)
        interface = options.get("interface", "swd")
        if interface not in ("swd", "jtag"):
            raise ValueError("Core monitor interface must be swd or jtag")
        settle_ms = options.get("settle_ms", 20)
        if not isinstance(settle_ms, int) or isinstance(settle_ms, bool) or not 0 <= settle_ms <= 1000:
            raise ValueError("settle_ms must be an integer between 0 and 1000")
        boot_timeout_ms = _int(options.get("boot_timeout_ms", 5000), "boot_timeout_ms")
        if not 100 <= boot_timeout_ms <= 30000:
            raise ValueError("boot_timeout_ms must be between 100 and 30000")
        policy = options.get("recovery_policy", "stop")
        if policy not in RECOVERY_POLICIES:
            raise ValueError("Core monitor recovery_policy is invalid")
        max_recoveries = _int(options.get("max_recoveries", 3), "max_recoveries")
        if not 0 <= max_recoveries <= 100:
            raise ValueError("max_recoveries must be an integer between 0 and 100")
        prefixes = options.get("expected_reset_prefixes", [])
        if not isinstance(prefixes, list):
            raise ValueError("expected_reset_prefixes must be a list of hexadecimal strings")
        try:
            parsed = tuple(bytes.fromhex(value) for value in prefixes)
        except (TypeError, ValueError) as exc:
            raise ValueError("expected_reset_prefixes must contain hexadecimal strings") from exc
        if any(not value for value in parsed):
            raise ValueError("expected_reset_prefixes cannot contain an empty prefix")
        return cls(core, interface, settle_ms, boot_timeout_ms, policy, max_recoveries, parsed)


def _int(value, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def select_backend(vendor_id: int, backend_classes: Mapping[str, type]) -> type:
    for backend in backend_classes.values():
        if (isinstance(backend, type) and issubclass(backend, DebugAccess)
                and vendor_id in debug_usb_vendor_ids(backend)):
            return backend
    raise ValueError(f"No debug backend drives USB vendor 0x{vendor_id:04x}")


class McuCoreSource:
    """A point source: each ``end()`` is one fresh sample of the core."""

    def __init__(self, entry: MonitorPlanEntry, *, profile: TargetProfile,
                 backend_class: type, options: McuCoreOptions):
        _, self.serial, _ = parse_usb_resource(entry.resource)
        self.entry = entry
        self.profile = profile
        self.options = options
        self.settle_ms = options.settle_ms
        self._backend_class = backend_class
        self._arch = arch_monitor(profile.arch)
        self._access: DebugAccess | None = None

    def open(self) -> None:
        access = self._backend_class()
        self._access = access
        access.attach(self.serial, self.profile.name, interface=self.options.interface)
        if self.profile.arch not in access.debug_architectures():
            raise ValueError(f"{self._backend_class.__name__} cannot reach {self.profile.arch} cores")

    def begin(self) -> None:
        """Nothing to mark: a core is read when asked."""

    def end(self) -> MonitorObservation:
        if self._access is None:
            raise RuntimeError("Monitor source is not open")
        observed_at = time.time()
        detail = self._arch.sample(self._access, self.profile, core=self.options.core)
        return self._observation(detail, observed_at)

    def snapshot(self) -> dict:
        if self._access is None:
            raise RuntimeError("Monitor source is not open")
        return self._arch.fault_snapshot(self._access, self.profile)

    def recover(self, expected: bool) -> dict:
        """Run the core and wait for two consecutive healthy samples.

        An expected reset already happened, so the core is only resumed if it
        stopped; any other recovery resets it. Two samples are needed because
        the first after a reset still carries the read-to-clear reset flag.
        """
        if self._access is None:
            raise RuntimeError("Monitor source is not open")
        reset = not expected
        started = time.monotonic()
        if reset:
            self._access.reset_core(halt=False)
        elif self._access.is_halted():
            self._access.resume()
        deadline = started + self.options.boot_timeout_ms / 1000
        last = None
        while time.monotonic() < deadline:
            last = self.end()
            if last["health"] == "ok":
                baseline = self.end()
                if baseline["health"] == "ok":
                    return {"recovered": True, "reset": reset,
                            "elapsed_ms": round((time.monotonic() - started) * 1000),
                            "baseline": baseline}
            time.sleep(0.05)
        return {"recovered": False, "reset": reset,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "last_observation": last,
                "error": "Target did not become ready before the recovery deadline"}

    def close(self) -> None:
        access, self._access = self._access, None
        if access is not None:
            access.detach()

    def _observation(self, detail: dict, observed_at: float) -> MonitorObservation:
        cause = detail["cause"]
        reasons = [cause] if cause else []
        return {
            "monitor": self.entry.name,
            "kind": KIND,
            "resource": self.entry.resource,
            "target": self.profile.name,
            "window": (observed_at, observed_at),
            "observed_at": observed_at,
            "health": mcu_core_health(detail["state"]),
            "reasons": reasons,
            "detail": detail,
        }


class McuCoreKind(MonitorKind):
    """The sampling side of ``mcu_core``; the campaign policy is added outside core."""

    KIND = KIND
    NAME = "MCU core"
    DESCRIPTION = ("Reads a CPU core's debug registers over SWD or JTAG to catch "
                   "faults, lockups, unexpected halts and resets.")
    DISPLAY = {"registers": "hex"}

    def __init__(self, context: MonitorContext, catalog: TargetCatalog | None = None):
        super().__init__(context)
        self.catalog = catalog or TargetCatalog.load_default()

    def parameters(self) -> dict:
        return {
            "resource": {"type": "str", "required": True, "description": "Debug probe",
                         "validation": {"choices": self._probes()}},
            "target": {"type": "str", "required": True, "description": "Target MCU",
                       "validation": {"choices": self.catalog.names()}},
            "interface": {"type": "str", "default": "swd", "description": "Debug interface",
                          "validation": {"choices": ["swd", "jtag"]}},
            "recovery_policy": {"type": "str", "default": "stop",
                                "description": "After a failure: stop the campaign, or reset the target and continue",
                                "validation": {"choices": list(RECOVERY_POLICIES)}},
            "max_recoveries": {"type": "int", "default": 3, "description": "Resets allowed per campaign",
                               "validation": {"min": 0, "max": 100}},
            "expected_reset_prefixes": {"type": "list", "default": [],
                                        "description": "Hex payload prefixes that are meant to reset the target"},
            "settle_ms": {"type": "int", "default": 20, "description": "Wait after a payload before sampling (ms)",
                          "validation": {"min": 0, "max": 1000}},
            "boot_timeout_ms": {"type": "int", "default": 5000, "description": "Time a recovery may take (ms)",
                                "validation": {"min": 100, "max": 30000}},
        }

    def validate(self, entry: MonitorPlanEntry) -> None:
        self._resolve(entry)

    def create(self, entry: MonitorPlanEntry) -> McuCoreSource:
        profile, options, backend = self._resolve(entry)
        return McuCoreSource(entry, profile=profile, backend_class=backend, options=options)

    def _resolve(self, entry: MonitorPlanEntry):
        vendor_id, _, function = parse_usb_resource(entry.resource)
        if function != "debug":
            raise ValueError("An mcu_core monitor needs a probe's debug function (…/debug)")
        profile = self.catalog.get(entry.target)
        options = McuCoreOptions.parse(entry.options, profile)
        return profile, options, select_backend(vendor_id, self.context.driver_classes())

    def _probes(self) -> list[dict]:
        """Every connected probe a debug backend drives, as ``{value, label}`` choices."""
        probes = []
        for name, driver_class in self.context.driver_classes().items():
            if not (isinstance(driver_class, type) and issubclass(driver_class, DebugAccess)):
                continue
            try:
                driver = driver_class()
                devices = driver.scan()
            except Exception as exc:
                # One absent SDK or unplugged probe must not hide the others.
                logger.warning("Debug probe scan with %s failed: %s", name, exc)
                continue
            for device in devices:
                resource = driver.resource_key(device)
                if resource:
                    probes.append({"value": resource, "label": device.name})
        return probes
