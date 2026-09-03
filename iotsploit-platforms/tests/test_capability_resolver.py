"""Tier-two capability results reflect short-lived host prerequisites."""

from __future__ import annotations

import pytest

from iotsploit_core.utils.exceptions import NotSupportedError
from iotsploit_platforms.adapters.capability_resolver import PlatformCapabilityResolver
from iotsploit_platforms.adapters.platforms.null.wifi_backend import NullWifiBackend

pytestmark = pytest.mark.unit


def test_binary_requirement_uses_the_shared_path_resolver(monkeypatch):
    resolver = PlatformCapabilityResolver()
    monkeypatch.setattr(resolver._paths, "resolve_tool_path", lambda name: f"/tools/{name}")

    assert resolver.resolve(("binary:nmap",)).available


def test_missing_binary_has_an_install_hint(monkeypatch):
    resolver = PlatformCapabilityResolver()
    monkeypatch.setattr(resolver._paths, "resolve_tool_path", lambda name: None)

    result = resolver.resolve(("binary:nmap",))

    assert not result.available
    assert "nmap" in result.reason
    assert result.hint


def test_unknown_requirement_is_blocked():
    result = PlatformCapabilityResolver().resolve(("device:unknown",))

    assert not result.available
    assert "Unknown" in result.reason


def test_null_wifi_backend_imports_and_explains_unsupported_operations():
    backend = NullWifiBackend(wifi_iface_name="wifi0")

    with pytest.raises(NotSupportedError, match="not supported"):
        backend.scan()
