"""The SOME/IP facet: what it stores, and what it deliberately does not.

Half of these assert absences. A facet that grows an address field, or a service
catalogue, does not fail any behavioural test -- it just quietly reintroduces the
problems the target model was restructured to remove. So the absences are
pinned here, each with the reason.
"""

from __future__ import annotations

import pytest

from iotsploit_core.domain.facet import FacetRegistry, RawFacet
from iotsploit_core.domain.target import Component
from iotsploit_protocols.someip import FACET_KEY, SomeipFacet, canonical_service_id

pytestmark = pytest.mark.unit


def component(**facets):
    return Component(component_id="c1", name="TCAM", type="ecu", facets=facets)


def test_the_facet_is_registered_under_someip():
    assert FacetRegistry.registered()[FACET_KEY] is SomeipFacet


def test_a_stored_payload_comes_back_typed():
    comp = component(someip={"port": 30509, "transport": "udp", "client_id": 0x1234})

    facet = comp.facet(FACET_KEY)

    assert isinstance(facet, SomeipFacet)
    assert facet.port == 30509
    assert facet.transport == "udp"
    assert facet.client_id == 0x1234


def test_defaults_survive_a_round_trip():
    dumped = component(someip={"port": 30509}).model_dump()["facets"]

    assert dumped[FACET_KEY] == {"port": 30509, "transport": "tcp", "client_id": None}


def test_an_empty_facet_is_valid():
    """Every field is optional: a component may speak SOME/IP on defaults alone."""
    assert isinstance(component(someip={}).facet(FACET_KEY), SomeipFacet)


def test_an_unusable_payload_degrades_instead_of_rejecting_the_component():
    comp = component(someip={"port": "not-a-port"})

    assert isinstance(comp.facet(FACET_KEY), RawFacet)
    assert comp.model_dump()["facets"][FACET_KEY] == {"port": "not-a-port"}


def test_an_unknown_field_is_preserved():
    """Written by a newer version of the plugin; must survive a round trip through this one."""
    comp = component(someip={"port": 30509, "future_field": "kept"})

    assert comp.model_dump()["facets"][FACET_KEY]["future_field"] == "kept"


def test_the_schema_declares_client_id_as_hex():
    """The facet knows its own conventions; core stays ignorant of what the numbers mean."""
    schema = SomeipFacet.model_json_schema()["properties"]

    assert schema["client_id"]["format"] == "hex"


def test_the_schema_is_published_for_the_editor():
    assert FACET_KEY in FacetRegistry.schemas()


# ── deliberate absences ───────────────────────────────────────────────────


def test_the_facet_holds_no_address():
    """A component already carries one, resolved in a single place by the binding layer.

    A second home for an address does not add capability -- it adds a question
    about which one wins, which is the wart facets exist to remove.
    """
    assert "host" not in SomeipFacet.model_fields
    assert "ip_address" not in SomeipFacet.model_fields


def test_the_facet_holds_no_service_catalogue():
    """A service/method list is a vendor description and belongs in the reference catalog.

    Same argument that keeps a production DBC out of CanFacet.
    """
    assert "services" not in SomeipFacet.model_fields
    assert "methods" not in SomeipFacet.model_fields


def test_the_facet_holds_no_sd_group():
    """The multicast group describes an Ethernet segment, not one component on it."""
    assert "sd_group" not in SomeipFacet.model_fields


def test_the_facet_holds_no_secrets():
    """Credentials stay in ClassifiedInfo/Env_Mgr, never copied into a JSON column."""
    assert not any(
        token in name for name in SomeipFacet.model_fields for token in ("pin", "secret", "passwd")
    )


# ── canonical ids ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "service, instance, expected",
    [
        (0x1234, 0x0001, "1234:0001"),
        (0x0001, 0x0001, "0001:0001"),
        (0xFFFF, 0xFFFF, "FFFF:FFFF"),
    ],
)
def test_the_canonical_id_is_zero_padded_uppercase(service, instance, expected):
    assert canonical_service_id(service, instance) == expected


def test_ids_that_differ_only_in_instance_stay_distinct():
    """Two instances of one service are two subjects; collapsing them loses a finding."""
    assert canonical_service_id(0x1234, 1) != canonical_service_id(0x1234, 2)
