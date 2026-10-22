"""DoIP delegates its fixed host configuration to the bounded helper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from iotsploit_django.tools.doip_mgr import DoIP_Mgr
from iotsploit_django.tools.sat_utils import SAT_Exception
from iotsploit_priv import PrivilegedHelperUnavailable

pytestmark = pytest.mark.unit


def test_connect_configures_the_selected_interface_before_opening_socket(monkeypatch):
    calls = []

    def privileged(verb, args):
        calls.append((verb, args))
        return SimpleNamespace(ok=True, exit=0, stderr="")

    manager = DoIP_Mgr(privileged_call_fn=privileged)
    monkeypatch.setattr("iotsploit_django.tools.doip_mgr.DeviceInfo.doip_eth_name", "eth0")
    monkeypatch.setattr(manager, "_DoIP_Mgr__connect_doip_socket", lambda ip, port: True)

    assert manager.connect(user_confirm=False) is True
    assert calls == [("doip-config", {"iface": "eth0"})]


def test_missing_helper_keeps_the_install_hint_in_the_public_error(monkeypatch):
    def unavailable(verb, args):
        raise PrivilegedHelperUnavailable("helper unavailable; run priv install")

    manager = DoIP_Mgr(privileged_call_fn=unavailable)
    monkeypatch.setattr("iotsploit_django.tools.doip_mgr.DeviceInfo.doip_eth_name", "eth0")

    with pytest.raises(SAT_Exception, match="priv install"):
        manager.connect(user_confirm=False)


def test_rejected_configuration_does_not_open_the_doip_socket(monkeypatch):
    manager = DoIP_Mgr(
        privileged_call_fn=lambda verb, args: SimpleNamespace(ok=False, exit=2, stderr="invalid interface")
    )
    monkeypatch.setattr("iotsploit_django.tools.doip_mgr.DeviceInfo.doip_eth_name", "bad")
    monkeypatch.setattr(
        manager,
        "_DoIP_Mgr__connect_doip_socket",
        lambda ip, port: pytest.fail("socket must not open after configuration failure"),
    )

    with pytest.raises(SAT_Exception, match="invalid interface"):
        manager.connect(user_confirm=False)
