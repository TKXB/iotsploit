import runpy
import sys
from pathlib import Path

import pytest

if sys.platform != "linux":
    pytest.skip("the native privileged helper is Linux-only", allow_module_level=True)

pytestmark = pytest.mark.unit

from iotsploit_priv.client import VERB_TABLE_HASH
from iotsploit_priv import native


ROOT = Path(__file__).resolve().parents[1]


def _daemon_namespace():
    path = ROOT / "privd/iotsploit-privd"
    return runpy.run_path(str(path))


def test_native_assets_are_complete_and_daemon_contract_matches_client():
    assert native.INSTALLER.is_file()
    assert all(source.is_file() for source, _, _ in native.install_manifest())
    assert _daemon_namespace()["VERB_TABLE_HASH"] == VERB_TABLE_HASH


def test_native_status_returns_absent_when_no_install_artifact_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(native, "DAEMON_DESTINATION", tmp_path / "daemon")
    monkeypatch.setattr(native, "UNIT_DESTINATIONS", (tmp_path / "socket", tmp_path / "service"))

    status = native.native_status(socket_path=tmp_path / "priv.sock")

    assert status.code == 1
    assert "not installed" in status.lines[0]


def test_systemd_units_apply_the_exact_native_capability_bounds():
    service = (ROOT / "systemd/iotsploit-privd.service").read_text()
    worker = (ROOT / "systemd/iotsploit-worker-capabilities.conf").read_text()
    socket_unit = (ROOT / "systemd/iotsploit-privd.socket").read_text()

    assert "CapabilityBoundingSet=CAP_NET_ADMIN" in service
    assert "AmbientCapabilities=CAP_NET_ADMIN" in service
    assert "CAP_NET_RAW" not in service
    assert "CapabilityBoundingSet=CAP_NET_RAW" in worker
    assert "CAP_NET_ADMIN" not in worker
    assert "SocketMode=0660" in socket_unit
    assert "SocketGroup=iotsploit" in socket_unit


def test_installer_is_standalone_and_has_only_fixed_destinations():
    installer = (ROOT / "install/iotsploit-priv-install").read_text()

    assert "import iotsploit" not in installer
    assert "/usr/local/libexec/iotsploit-privd" in installer
    assert "/etc/systemd/system" in installer


def test_status_defaults_to_the_invoking_account(monkeypatch):
    """Django runs as the invoking user on both rigs; www-data is container-only."""
    monkeypatch.setattr(native, "current_user", lambda: "rig-operator")
    seen = {}

    def _identity(service_user):
        seen["user"] = service_user
        raise KeyError(service_user)

    monkeypatch.setattr(native, "_service_identity", _identity)
    monkeypatch.setattr(native.Path, "exists", lambda _self: True)

    native.native_status()

    assert seen["user"] == "rig-operator"


def test_permission_denied_names_the_group_not_the_daemon(tmp_path, monkeypatch):
    """A caller outside the iotsploit group must not read as a broken daemon."""
    monkeypatch.setattr(native, "current_user", lambda: "rig-operator")
    unreachable = tmp_path / "priv.sock"

    def _refuse(self, _address):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(native.socket.socket, "connect", _refuse)

    kind, detail = native._health_probe(unreachable)

    assert kind == "permission"
    assert "permission denied" in detail
    assert "rig-operator" in detail


class FakeGroup:
    def __init__(self, gid: int, members: tuple[str, ...]):
        self.gr_gid = gid
        self.gr_mem = list(members)


def test_membership_granted_but_session_is_stale_says_so(monkeypatch):
    """The install succeeded; only the shell that ran it is out of date."""
    monkeypatch.setattr(native.os, "getgroups", lambda: [1000])

    message = native._permission_diagnosis("tkxb", FakeGroup(999, ("tkxb",)))

    assert "log out and back in" in message
    assert "newgrp iotsploit" in message


def test_membership_never_granted_points_at_the_install_command(monkeypatch):
    monkeypatch.setattr(native.os, "getgroups", lambda: [1000])

    message = native._permission_diagnosis("tkxb", FakeGroup(999, ("www-data",)))

    assert "priv install --service-user tkxb" in message
