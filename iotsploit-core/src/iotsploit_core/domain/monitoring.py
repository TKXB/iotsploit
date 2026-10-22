"""What a target monitor saw, for every kind of monitor.

A monitor watches the device under test while a campaign runs: its CPU core
over JTAG/SWD today, and later its UART console, supply rails or BLE radio.
Every kind reports the same envelope, so the harness, the recorder, the event
stream and the UI can handle a kind they have never seen. Everything specific
to one kind goes in ``detail``.

An observation says what was seen, never what it means. Whether a reading is a
crash, a hang or an expected reset is decided by the campaign's policy for that
monitor, which also knows the payload that preceded it.

Resource keys name the piece of hardware a monitor holds exclusively. They
carry the *function* as well as the device, because one USB device can expose
independent functions: a J-Link's debug port and its VCOM UART are separate
resources on the same probe. The Rust boundary-scan bridge builds the same key
for the same probe, so both runtimes contend for one lock.

This module must stay free of I/O, persistence and Django imports.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict

Health = Literal["ok", "degraded", "fault", "down", "reset", "unavailable"]
HEALTH_VALUES: tuple[str, ...] = ("ok", "degraded", "fault", "down", "reset", "unavailable")


class MonitorObservation(TypedDict):
    monitor: str
    """Plan-entry name, unique within a campaign: ``mcu_core:main``."""
    kind: str
    """``mcu_core`` today; ``uart``, ``power``, ``ble`` later. An open set."""
    resource: str
    """The lease key of the hardware this monitor holds."""
    target: str
    window: tuple[float, float]
    """Wall-clock start and end of what this covers; a point sample has start == end."""
    observed_at: float
    """Equal to ``window[1]``."""
    health: Health
    reasons: list[str]
    """Human-readable causes behind ``health``; empty when healthy."""
    detail: dict
    """Exactly one detail type, chosen by ``kind``."""


class McuCoreDetail(TypedDict):
    """One sample of a CPU core read over a debug probe."""

    core: str
    state: str
    """running | sleeping | halted | fault | lockup | reset | unavailable"""
    cause: Optional[str]
    """The sampler's explanation of ``state``; None when the core is healthy."""
    fault_causes: list[str]
    active_exception: Optional[int]
    retired: Optional[bool]
    reset_observed: Optional[bool]
    registers: dict
    arch: str
    sample_started: float
    sample_ended: float


MCU_CORE_STATES: tuple[str, ...] = (
    "running", "sleeping", "halted", "fault", "lockup", "reset", "unavailable",
)

_STATE_HEALTH: dict[str, Health] = {
    "running": "ok",
    "sleeping": "ok",
    "halted": "degraded",
    "fault": "fault",
    "lockup": "fault",
    "reset": "reset",
    "unavailable": "unavailable",
}


def mcu_core_health(state: str) -> Health:
    return _STATE_HEALTH.get(state, "unavailable")


def normalize_serial(serial: str) -> str:
    """One spelling per probe, whichever library enumerated it.

    pylink reports a J-Link as ``1050298903``; its USB descriptor, which probe-rs
    reads, says ``001050298903``. Numeric serials drop leading zeros; anything
    else is kept as reported.
    """
    text = str(serial).strip()
    if text.isdigit():
        return str(int(text))
    return text


def usb_resource(vendor_id: int, serial: str, function: str) -> str:
    """``usb:1366-1050298903/debug`` for function ``debug`` of a J-Link."""
    if not function or "/" in function:
        raise ValueError("A resource function is a single word such as 'debug' or 'vcom'")
    normalized = normalize_serial(serial)
    if not normalized:
        raise ValueError("A USB resource needs the device's serial number")
    return f"usb:{vendor_id:04x}-{normalized}/{function}"


def parse_usb_resource(resource: str) -> tuple[int, str, str]:
    """Inverse of :func:`usb_resource`: ``(vendor_id, serial, function)``."""
    if not isinstance(resource, str) or not resource.startswith("usb:"):
        raise ValueError(f"Not a USB resource: {resource!r}")
    body, _, function = resource[4:].partition("/")
    vendor, _, serial = body.partition("-")
    try:
        vendor_id = int(vendor, 16)
    except ValueError as exc:
        raise ValueError(f"Invalid vendor id in resource {resource!r}") from exc
    if not serial or not function:
        raise ValueError(f"Resource {resource!r} must look like usb:<vid>-<serial>/<function>")
    return vendor_id, normalize_serial(serial), function
