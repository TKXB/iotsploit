"""The monitor kinds this package ships.

They are registered under the ``iotsploit.monitors`` entry-point group, the
same way a third-party kind is, so nothing lists them by name.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Mapping

from iotsploit_core.core.monitoring.kind import MonitorKind
from iotsploit_core.core.monitoring.source import MonitorPlanEntry
from iotsploit_core.core.monitoring.sources.mcu_core import McuCoreKind, McuCoreSource
from iotsploit_core.domain.monitoring import MonitorObservation
from iotsploit_fuzzer.monitors import McuCoreMonitor

USB_DEVICES = Path("/sys/bus/usb/devices")
PORT_PREFIX = "usb-port:"
# Kernel log phrases about one USB device, most severe first.
KERNEL_RESETS = ("USB disconnect", "reset ")
KERNEL_ERRORS = ("error", "over-current", "unable to enumerate", "not accepting address")


class McuCore(McuCoreKind):
    """A core source paired with the fuzzer policy for it."""

    def policy(self, source: McuCoreSource) -> McuCoreMonitor:
        options = source.options
        return McuCoreMonitor(
            source.entry.name,
            source.end,
            source.settle_ms,
            snapshot=source.snapshot,
            recover=source.recover,
            recovery_policy=options.recovery_policy,
            max_recoveries=options.max_recoveries,
            expected_reset_prefixes=options.expected_reset_prefixes,
        )


def _usb_device(port: str) -> dict | None:
    """What sysfs says about the device on ``port`` (``1-4.3``); None when nothing is there."""
    node = USB_DEVICES / port

    def read(name: str) -> str:
        try:
            return (node / name).read_text().strip()
        except OSError:
            return ""

    if not read("idVendor"):
        return None
    return {"vid_pid": f"{read('idVendor')}:{read('idProduct')}", "product": read("product"),
            "serial": read("serial"), "devnum": read("devnum"), "speed": read("speed"),
            "device_class": read("bDeviceClass")}


class UsbStatusSource:
    """A window source: each ``end()`` covers the time since the last mark, then marks again.

    The default health policy only calls ``end()``, before and after a payload,
    so the window before a case also catches what happened between cases.
    """

    def __init__(self, entry: MonitorPlanEntry, settle_ms: int, kernel_log: bool):
        self.entry = entry
        self.port = entry.resource.removeprefix(PORT_PREFIX)
        self.settle_ms = settle_ms
        self._kernel_log = kernel_log
        self._journal = None
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def open(self) -> None:
        self._expected = _usb_device(self.port)
        if self._expected is None:
            raise ValueError(f"No USB device on port {self.port}")
        if self._kernel_log:
            # -n 0: only lines logged from now on.
            self._journal = subprocess.Popen(
                ["journalctl", "-k", "-f", "-n", "0", "-o", "cat"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            threading.Thread(target=self._follow, args=(self._journal,), daemon=True).start()
        self.begin()

    def _follow(self, journal) -> None:
        tag = f" {self.port}:"
        for line in journal.stdout:
            if tag in line:
                with self._lock:
                    self._lines.append(line.rstrip())

    def begin(self) -> None:
        self._started = time.time()
        with self._lock:
            self._lines.clear()

    def end(self) -> MonitorObservation:
        observed_at = time.time()
        started = self._started
        with self._lock:
            lines, self._lines = self._lines[-50:], []
        self._started = observed_at
        device = _usb_device(self.port)
        expected = self._expected
        health, reasons = "ok", []
        if self._journal is not None and self._journal.poll() is not None:
            health, reasons = "unavailable", ["The kernel log reader stopped"]
        elif device is None:
            health, reasons = "down", [f"USB device on port {self.port} disconnected"]
        elif device["vid_pid"] != expected["vid_pid"]:
            health, reasons = "fault", [f"Port {self.port} now holds {device['vid_pid']}, "
                                        f"not {expected['vid_pid']}"]
        elif device["devnum"] != expected["devnum"] or any(
                phrase in line for line in lines for phrase in KERNEL_RESETS):
            health, reasons = "reset", [f"USB device on port {self.port} was reset or re-enumerated"]
        elif device["speed"] != expected["speed"]:
            health, reasons = "degraded", [f"USB speed changed from {expected['speed']} "
                                           f"to {device['speed']} Mb/s"]
        elif any(phrase in line.lower() for line in lines for phrase in KERNEL_ERRORS):
            health, reasons = "degraded", ["The kernel logged USB errors for this device"]
        return {
            "monitor": self.entry.name,
            "kind": UsbStatus.KIND,
            "resource": self.entry.resource,
            "target": self.entry.target,
            "window": (started, observed_at),
            "observed_at": observed_at,
            "health": health,
            "reasons": reasons,
            "detail": {"port": self.port, "expected": expected, "device": device, "kernel_lines": lines},
        }

    def recover(self, expected: bool) -> dict:
        return {"recovered": False, "error": "A USB status monitor cannot recover the device"}

    def close(self) -> None:
        journal, self._journal = self._journal, None
        if journal is not None:
            journal.terminate()
            journal.wait()
            journal.stdout.close()


class UsbStatus(MonitorKind):
    KIND = "usb_status"
    NAME = "USB status"
    DESCRIPTION = ("Watches how the host sees a USB device: disconnects, resets, re-enumeration, "
                   "speed changes and kernel USB errors. Linux only; never opens the device.")
    DISPLAY = {"expected": "json", "device": "json", "kernel_lines": "json"}

    def parameters(self, values: Mapping) -> dict:
        return {
            "resource": {"type": "str", "required": True, "description": "USB device, by port",
                         "validation": {"choices": self._devices()}},
            "kernel_log": {"type": "bool", "default": True,
                           "description": "Also read the kernel log (needs the adm or systemd-journal group)"},
            "settle_ms": {"type": "int", "default": 50, "description": "Wait after a payload before checking (ms)",
                          "validation": {"min": 0, "max": 5000}},
        }

    def validate(self, entry: MonitorPlanEntry) -> None:
        if not sys.platform.startswith("linux"):
            raise ValueError("The USB status monitor runs on Linux only")
        port = entry.resource.removeprefix(PORT_PREFIX)
        if not entry.resource.startswith(PORT_PREFIX) or not port or "/" in port or ":" in port:
            raise ValueError("A usb_status monitor needs a USB port resource (usb-port:<bus>-<ports>)")
        settle_ms = entry.options.get("settle_ms", 50)
        if type(settle_ms) is not int or not 0 <= settle_ms <= 5000:
            raise ValueError("settle_ms must be an integer between 0 and 5000")
        if type(entry.options.get("kernel_log", True)) is not bool:
            raise ValueError("kernel_log must be true or false")

    def create(self, entry: MonitorPlanEntry) -> UsbStatusSource:
        return UsbStatusSource(entry, entry.options.get("settle_ms", 50), entry.options.get("kernel_log", True))

    @staticmethod
    def _devices() -> list[dict]:
        """Every connected USB device except hubs, as ``{value, label}`` choices."""
        choices = []
        for node in sorted(USB_DEVICES.glob("[0-9]*-*")):
            if ":" in node.name:
                continue
            device = _usb_device(node.name)
            if device is None or device["device_class"] == "09":
                continue
            serial = f" serial {device['serial']}" if device["serial"] else ""
            choices.append({"value": PORT_PREFIX + node.name,
                            "label": f"{device['vid_pid']} {device['product']}{serial} on port {node.name}"})
        return choices
