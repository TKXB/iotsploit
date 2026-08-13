"""The facet mechanism.

The rule these protect is that configuration is never lost. A facet key whose
plugin is uninstalled, not yet loaded, or newer than this backend must still
round-trip verbatim -- otherwise removing a plugin silently destroys the
configuration of every target that used it.
"""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import SecretStr

from iotsploit_core.domain.facet import Facet, FacetRegistry, RawFacet, register_facet
from iotsploit_core.domain.target import Component, ComponentFactory, Vehicle

pytestmark = pytest.mark.unit


class DoipFacet(Facet):
    logical_address: int
    port: int = 13400
    security_pin: Optional[SecretStr] = None


@pytest.fixture
def doip():
    """Register a facet the way a plugin would, and restore what was there.

    The registry is process-global, so a teardown that just unregisters would
    delete a real registration made at import by whichever plugin owns the key
    -- breaking other tests only when the suite runs in the right order.
    """
    previous = FacetRegistry.registered().get("doip")
    FacetRegistry.register("doip", DoipFacet)
    yield DoipFacet
    if previous is None:
        FacetRegistry.unregister("doip")
    else:
        FacetRegistry.register("doip", previous)


def component(**facets):
    return Component(component_id="c1", name="TCAM", type="ecu", facets=facets)


# ---------------- registered facets ----------------


def test_a_registered_facet_is_typed_and_validated(doip):
    comp = component(doip={"logical_address": 0x1011})

    assert isinstance(comp.facet("doip"), DoipFacet)
    assert comp.facet("doip").logical_address == 0x1011
    assert comp.facet("doip").port == 13400


def test_defaults_survive_serialization(doip):
    """Dict[str, Facet] serializes against the declared type without
    SerializeAsAny, which would drop every subclass field."""
    dumped = component(doip={"logical_address": 0x1011}).model_dump()["facets"]

    assert dumped["doip"] == {"logical_address": 0x1011, "port": 13400, "security_pin": None}


def test_a_facet_survives_a_full_round_trip(doip):
    original = component(doip={"logical_address": 0x1011})
    reloaded = Component(**original.model_dump())

    assert isinstance(reloaded.facet("doip"), DoipFacet)
    assert reloaded.facet("doip").logical_address == 0x1011


def test_the_registry_publishes_a_schema(doip):
    """This is what a schema-driven editor renders instead of a key/value box."""
    schema = FacetRegistry.schemas()["doip"]

    assert schema["properties"]["logical_address"]["type"] == "integer"
    assert "logical_address" in schema["required"]


# ---------------- never lose configuration ----------------


def test_an_unknown_key_round_trips_verbatim():
    """The plugin owning this key is not installed here."""
    payload = {"service_id": 0x1234, "instances": [{"id": 1}], "nested": {"a": True}}
    comp = component(someip=payload)

    assert isinstance(comp.facet("someip"), RawFacet)
    assert comp.model_dump()["facets"]["someip"] == payload


def test_unregistering_degrades_but_keeps_the_data(doip):
    """Uninstalling a plugin must not destroy what it configured."""
    stored = component(doip={"logical_address": 0x1011}).model_dump()
    FacetRegistry.unregister("doip")

    degraded = Component(**stored)
    assert isinstance(degraded.facet("doip"), RawFacet)
    assert degraded.model_dump()["facets"]["doip"]["logical_address"] == 0x1011


def test_an_invalid_stored_facet_degrades_rather_than_rejecting(doip):
    """A row written before a schema change must still load."""
    comp = component(doip={"logical_address": "not-an-int"})

    assert isinstance(comp.facet("doip"), RawFacet)
    assert comp.model_dump()["facets"]["doip"] == {"logical_address": "not-an-int"}


def test_constructing_a_registered_facet_directly_still_validates(doip):
    with pytest.raises(Exception):
        DoipFacet(logical_address="not-an-int")


def test_an_unexpected_field_is_kept(doip):
    """A newer version of the plugin may write fields this one does not know."""
    comp = component(doip={"logical_address": 0x1011, "future_field": "kept"})

    assert comp.model_dump()["facets"]["doip"]["future_field"] == "kept"


# ---------------- integration with components and targets ----------------


def test_facets_reach_the_target_dump(doip):
    comp = component(doip={"logical_address": 0x1011})
    target = Vehicle(target_id="t1", name="T", type="vehicle", components=[comp])

    assert target.model_dump()["components"][0]["facets"]["doip"]["logical_address"] == 0x1011


def test_the_component_factory_passes_facets_through(doip):
    comp = ComponentFactory.create_component(
        {"component_id": "c1", "name": "TCAM", "type": "ecu", "facets": {"doip": {"logical_address": 0x1011}}}
    )

    assert isinstance(comp.facet("doip"), DoipFacet)


def test_a_component_without_facets_is_unchanged():
    comp = Component(component_id="c1", name="X", type="generic")

    assert comp.facets == {} and comp.facet("doip") is None


def test_registering_a_non_facet_is_refused():
    with pytest.raises(TypeError):
        FacetRegistry.register("bad", dict)


def test_the_decorator_registers_the_class():
    @register_facet("temp_test_facet")
    class TempFacet(Facet):
        value: int = 0

    try:
        assert FacetRegistry.registered()["temp_test_facet"] is TempFacet
    finally:
        FacetRegistry.unregister("temp_test_facet")
