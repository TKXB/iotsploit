"""Compatibility checks are deterministic and never import optional modules."""

from __future__ import annotations

import pytest

from iotsploit_core.platforms.capability import static_compatibility
from iotsploit_core.platforms.consts import WINDOWS

pytestmark = pytest.mark.unit


def test_empty_requirements_are_available():
    assert static_compatibility(()).available


def test_installed_module_is_available():
    assert static_compatibility(("module:json",)).available


def test_missing_module_explains_how_to_fix_it():
    result = static_compatibility(("module:iotsploit_module_that_does_not_exist",))

    assert not result.available
    assert "not installed" in result.reason
    assert result.hint


def test_tier_two_requirement_is_deferred():
    assert static_compatibility(("binary:nmap",)) is None


def test_invalid_requirement_is_blocked():
    result = static_compatibility(("broken",))

    assert not result.available
    assert "Invalid" in result.reason


def test_unsupported_platform_is_blocked():
    platform = "linux" if WINDOWS else "windows"
    result = static_compatibility((f"platform:{platform}",))

    assert not result.available
    assert "requires" in result.reason
