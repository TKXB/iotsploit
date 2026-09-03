"""Network tools receive validated argv and only owned jobs are stopped."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from iotsploit_django.tools.net_audit_mgr import (
    NetAudit_Mgr,
    validate_ipv4_hosts,
    validate_port_spec,
)

pytestmark = pytest.mark.unit


def test_host_discovery_uses_privileged_nmap_argv():
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="Nmap scan report for 192.0.2.1\n", stderr="")

    manager = NetAudit_Mgr(run=run, resolve_binary=lambda name: f"/usr/bin/{name}")

    result = manager.ip_detect(["192.0.2.0/24"])

    assert result == ["192.0.2.1"]
    assert calls[0][0] == ["/usr/bin/nmap", "-sn", "--privileged", "192.0.2.0/24"]
    assert calls[0][1]["stdin"] is subprocess.DEVNULL
    assert "shell" not in calls[0][1]


def test_port_scan_uses_connect_scan_and_parses_stdout_xml():
    xml = (
        '<nmaprun><host><address addr="192.0.2.1" addrtype="ipv4"/>'
        '<ports><port protocol="tcp" portid="443"><state state="open"/></port></ports>'
        "</host></nmaprun>"
    )
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=xml, stderr="")

    manager = NetAudit_Mgr(run=run, resolve_binary=lambda name: f"/usr/bin/{name}")

    result = manager.port_detect(["192.0.2.1"], [22, 443])

    assert result == [{"ip": "192.0.2.1", "port": "443"}]
    assert calls[0] == [
        "/usr/bin/nmap",
        "-vv",
        "-sT",
        "-T2",
        "-p",
        "22,443",
        "192.0.2.1",
        "-oX",
        "-",
    ]


@pytest.mark.parametrize(
    "hosts",
    [["192.0.2.1;id"], ["10.0.0.0/8"], ["::1"], ["192.0.2.1"] * 257, "192.0.2.1"],
)
def test_host_validation_rejects_unsafe_or_unbounded_values(hosts):
    with pytest.raises(ValueError):
        validate_ipv4_hosts(hosts)


@pytest.mark.parametrize("ports", ["0", "65536", "443-22", "22;id", [], None])
def test_port_validation_rejects_invalid_values(ports):
    with pytest.raises(ValueError):
        validate_port_spec(ports)


class FakeProcess:
    def __init__(self) -> None:
        self.running = True
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout):
        if self.running:
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0

    def kill(self):
        self.killed = True
        self.running = False


def test_stopping_one_attack_never_signals_another(monkeypatch):
    calls = []
    processes = []

    def popen(argv, **kwargs):
        process = FakeProcess()
        calls.append((argv, kwargs))
        processes.append(process)
        return process

    manager = NetAudit_Mgr(popen=popen, resolve_binary=lambda name: f"/usr/bin/{name}")
    manager.start_mac_flood_attack("192.0.2.10", "eth0")
    manager.start_tcp_flood_attack("192.0.2.11")

    manager.stop_mac_flood_attack()

    assert processes[0].terminated is True
    assert processes[1].terminated is False
    assert calls[0][0] == ["/usr/bin/macof", "-i", "eth0", "-d", "192.0.2.10"]
    assert calls[0][1] == {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
        "close_fds": True,
    }
