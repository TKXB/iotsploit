"""The pre-monitor-set wire format, kept for clients built before it.

Until the Flutter monitor workspace speaks ``monitors`` plans and envelopes, it
sends a single ``core_monitor`` object and reads a flat ``core_observation``
dict (``state``, ``observed_at``, ``stop_reason``, ``detected_reason`` at the
top level). Target history also stores that flat dict as the ``core_state``
fact value, and changing its shape would break comparisons with earlier scans.

This module is the only place that knows the old shape: one translation in,
one flattening out.
"""

from __future__ import annotations

from typing import Optional

from iotsploit_core.domain.monitoring import parse_usb_resource, usb_resource

SEGGER_USB_VENDOR_ID = 0x1366
LEGACY_MONITOR_NAME = "mcu_core"
LEGACY_MONITOR_ID = "mcu-core"


def _legacy_int(config: dict, key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def legacy_plan(core_monitor) -> list[dict]:
    """``core_monitor`` (one probe's core) as a one-entry ``monitors`` plan.

    ``probe_vendor_id`` selects the probe's backend; clients that predate it
    only had J-Links.
    """
    if not isinstance(core_monitor, dict):
        raise ValueError("core_monitor must be an object")
    serial = str(core_monitor.get("probe_serial", "")).strip()
    if not serial.isalnum() or not serial.strip("0"):
        raise ValueError("A debug probe serial is required")
    vendor_id = _legacy_int(core_monitor, "probe_vendor_id", SEGGER_USB_VENDOR_ID)
    options = {
        "settle_ms": _legacy_int(core_monitor, "settle_ms", 20),
        "boot_timeout_ms": _legacy_int(core_monitor, "boot_timeout_ms", 5000),
        "max_recoveries": _legacy_int(core_monitor, "max_recoveries", 3),
        "recovery_policy": core_monitor.get("recovery_policy", "stop"),
        "expected_reset_prefixes": core_monitor.get("expected_reset_prefixes", []),
    }
    return [{
        "kind": "mcu_core",
        "name": LEGACY_MONITOR_NAME,
        "resource": usb_resource(vendor_id, serial, "debug"),
        "target": str(core_monitor.get("target_device") or ""),
        "target_id": str(core_monitor.get("target_id", "") or "").strip(),
        "options": options,
    }]


def flatten_mcu_core(observation: Optional[dict]) -> Optional[dict]:
    """An ``mcu_core`` envelope in the flat shape of a pre-envelope observation."""
    if not isinstance(observation, dict) or "detail" not in observation:
        return observation
    detail = observation["detail"]
    try:
        _, probe_serial, _ = parse_usb_resource(observation["resource"])
    except (KeyError, ValueError):
        probe_serial = None
    return {
        "target": observation.get("target"),
        "probe_serial": probe_serial,
        "observed_at": observation.get("observed_at"),
        "sample_started": detail.get("sample_started"),
        "registers": detail.get("registers", {}),
        "state": detail.get("state"),
        "crashed": detail.get("state") == "lockup",
        "stop_reason": detail.get("cause"),
        "retired": detail.get("retired"),
        "reset_observed": detail.get("reset_observed"),
        "active_exception": detail.get("active_exception"),
        "fault_causes": detail.get("fault_causes", []),
        "sample_ended": detail.get("sample_ended"),
    }


def _flatten_recovery(recovery: dict) -> dict:
    flat = dict(recovery)
    for key in ("baseline", "last_observation"):
        if key in flat:
            flat[key] = flatten_mcu_core(flat[key])
    return flat


def legacy_core_observation(verdict: dict) -> dict:
    """An ``mcu_core`` verdict as the flat ``core_observation`` a harness used to return."""
    flat = flatten_mcu_core(verdict["observation"])
    flat["crashed"] = verdict["verdict"] == "crash"
    flat["stop_reason"] = verdict.get("stop_reason")
    if verdict.get("before") is not None:
        flat["before"] = flatten_mcu_core(verdict["before"])
    evidence = verdict.get("evidence") or {}
    if "confirmation" in evidence:
        flat["confirmation"] = flatten_mcu_core(evidence["confirmation"])
    if "expected_reset" in evidence:
        flat["expected_reset"] = evidence["expected_reset"]
    if "snapshot" in evidence:
        flat["snapshot"] = evidence["snapshot"]
    if "recovery" in evidence:
        flat["recovery"] = _flatten_recovery(evidence["recovery"])
    if verdict.get("before") is not None and verdict.get("detected_reason"):
        flat["detected_reason"] = verdict["detected_reason"]
    return flat


def first_mcu_core(verdicts: list[dict]) -> Optional[dict]:
    return next((verdict for verdict in verdicts if verdict.get("kind") == "mcu_core"), None)
