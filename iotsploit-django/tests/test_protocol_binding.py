"""Resolving a protocol client from the current target.

The behaviour worth pinning is what happens when configuration is *missing*.
The old DoIP code answered that question with `ip="169.254.19.1"` as a function
default, so an unconfigured bench silently probed one particular vehicle's
gateway and reported its silence as a result. Every "no default" test below
exists so that cannot come back.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_core.domain.target import Component, Vehicle  # noqa: E402
from iotsploit_django.adapters.django.protocol_binding import (  # noqa: E402
    component_address,
    component_named,
    someip_client_for,
    someip_config_for,
)
from iotsploit_protocols.errors import NotConfigured  # noqa: E402
from iotsploit_protocols.someip import SomeIpClient  # noqa: E402

pytestmark = pytest.mark.unit


class FakeManager:
    def __init__(self, target):
        self._target = target

    def get_current_target(self):
        return self._target


@pytest.fixture
def current(monkeypatch):
    """Swap in a target without touching the database."""

    def apply(target):
        import iotsploit_django.adapters.django.target_models as target_models

        monkeypatch.setattr(
            target_models.TargetManager, "get_instance", staticmethod(lambda: FakeManager(target))
        )

    return apply


def vehicle(*components):
    return Vehicle(target_id="t1", name="Zeekr", type="vehicle", components=list(components))


def ecu(name="TCAM", ip="198.18.34.10", **facets):
    properties = {"ip_address": ip} if ip else {}
    return Component(
        component_id=f"c_{name}", name=name, type="ecu", properties=properties, facets=facets
    )


# ── the happy path ────────────────────────────────────────────────────────


def test_a_configured_component_yields_a_config(current):
    current(vehicle(ecu(someip={"port": 30509, "transport": "udp", "client_id": 0x0ABC})))

    config = someip_config_for("TCAM")

    assert (config.host, config.port) == ("198.18.34.10", 30509)
    assert config.transport == "udp"
    assert config.client_id == 0x0ABC


def test_the_component_name_is_matched_case_insensitively(current):
    current(vehicle(ecu(name="tcam", someip={"port": 30509})))

    assert someip_config_for("TCAM").host == "198.18.34.10"


def test_the_client_is_not_connected_until_it_is_entered(current):
    """Building a config must not touch the network -- a plugin may build several."""
    current(vehicle(ecu(someip={"port": 30509})))

    client = someip_client_for("TCAM")

    assert isinstance(client, SomeIpClient)
    assert client._sock is None


def test_defaults_apply_when_the_facet_omits_them(current):
    current(vehicle(ecu(someip={"port": 30509})))

    config = someip_config_for("TCAM")

    assert config.transport == "tcp"
    assert config.client_id == 0x0001


# ── explicit arguments win ────────────────────────────────────────────────


def test_an_explicit_host_overrides_the_component(current):
    current(vehicle(ecu(someip={"port": 30509})))

    assert someip_config_for("TCAM", host="10.0.0.9").host == "10.0.0.9"


def test_an_explicit_port_overrides_the_facet(current):
    current(vehicle(ecu(someip={"port": 30509})))

    assert someip_config_for("TCAM", port=40000).port == 40000


def test_explicit_arguments_work_with_no_facet_at_all(current):
    """A parameter-driven plugin must not require the target to be configured first."""
    current(vehicle(ecu(ip=None)))

    config = someip_config_for("TCAM", host="10.0.0.9", port=40000)

    assert (config.host, config.port) == ("10.0.0.9", 40000)


# ── missing configuration fails loudly ────────────────────────────────────


def test_no_current_target_is_an_error_not_a_default(current):
    current(None)

    with pytest.raises(NotConfigured, match="no component named"):
        someip_config_for("TCAM")


def test_an_unknown_component_is_an_error(current):
    current(vehicle(ecu(name="DHU", someip={"port": 30509})))

    with pytest.raises(NotConfigured, match="no component named 'TCAM'"):
        someip_config_for("TCAM")


def test_a_component_without_an_address_never_gets_a_guessed_one(current):
    current(vehicle(ecu(ip=None, someip={"port": 30509})))

    with pytest.raises(NotConfigured, match="no ip_address"):
        someip_config_for("TCAM")


def test_a_component_without_a_port_is_not_given_the_sd_port(current):
    """30490 is service discovery; an application endpoint's port is per-deployment."""
    current(vehicle(ecu()))

    with pytest.raises(NotConfigured, match="no SOME/IP port"):
        someip_config_for("TCAM")


def test_an_empty_ecu_name_is_an_error(current):
    current(vehicle(ecu()))

    with pytest.raises(NotConfigured, match="no component named"):
        someip_config_for("")


# ── degraded stored data ──────────────────────────────────────────────────


def test_an_unusable_facet_is_treated_as_unconfigured(current):
    """A payload that failed validation loads as RawFacet; reading a port off it would lie."""
    current(vehicle(ecu(someip={"port": "not-a-port"})))

    with pytest.raises(NotConfigured, match="no SOME/IP port"):
        someip_config_for("TCAM")


def test_an_unusable_facet_still_allows_an_explicit_port(current):
    current(vehicle(ecu(someip={"port": "not-a-port"})))

    assert someip_config_for("TCAM", port=30509).port == 30509


# ── address lookup ────────────────────────────────────────────────────────


def test_the_address_comes_from_properties_or_the_typed_field():
    from iotsploit_core.domain.target import NetworkComponent

    typed = NetworkComponent(
        component_id="c2", name="ETH", type="network", ip_address="198.18.34.20"
    )

    assert component_address(ecu(ip="198.18.34.10")) == "198.18.34.10"
    assert component_address(typed) == "198.18.34.20"


def test_component_named_returns_none_without_a_target(current):
    current(None)

    assert component_named("TCAM") is None
