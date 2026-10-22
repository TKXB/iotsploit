"""The DoIP facet, and the fallback that keeps unconfigured setups working.

Nothing here migrates data, so every existing target has no "doip" facet. The
built-in constants must therefore stay reachable, and the facet must win only
where one is actually configured.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from pydantic import ValidationError  # noqa: E402

from iotsploit_core.domain.facet import FacetRegistry  # noqa: E402
from iotsploit_core.domain.target import Component, Vehicle  # noqa: E402
from iotsploit_django.tools import doip_facet as mod  # noqa: E402
from iotsploit_django.tools.doip_facet import DoipFacet, doip_facet_for, logical_address_for  # noqa: E402

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

        monkeypatch.setattr(target_models.TargetManager, "get_instance", staticmethod(lambda: FakeManager(target)))

    return apply


def vehicle(*components):
    return Vehicle(target_id="t1", name="Zeekr", type="vehicle", components=list(components))


def ecu(name, **facets):
    return Component(component_id=f"c_{name}", name=name, type="ecu", facets=facets)


def test_the_facet_is_registered_under_doip():
    assert FacetRegistry.registered()["doip"] is DoipFacet


def test_a_configured_facet_wins(current):
    current(vehicle(ecu("TCAM", doip={"logical_address": 0x2002})))

    assert logical_address_for("tcam", 0x1011) == 0x2002


def test_an_unconfigured_component_falls_back(current):
    """Every existing target is in this state; the default must still work."""
    current(vehicle(ecu("TCAM")))

    assert logical_address_for("tcam", 0x1011) == 0x1011


def test_a_missing_component_falls_back(current):
    current(vehicle(ecu("DHU", doip={"logical_address": 0x2002})))

    assert logical_address_for("tcam", 0x1011) == 0x1011


def test_no_current_target_falls_back(current):
    current(None)

    assert logical_address_for("tcam", 0x1011) == 0x1011


def test_component_names_match_case_insensitively(current):
    current(vehicle(ecu("tcam", doip={"logical_address": 0x2002})))

    assert logical_address_for("TCAM", 0x1011) == 0x2002


def test_an_unusable_stored_facet_falls_back(current):
    """A payload that fails validation degrades to RawFacet; using it as an
    address would send UDS frames to a nonsense target."""
    current(vehicle(ecu("TCAM", doip={"logical_address": "not-an-int"})))

    assert doip_facet_for("tcam") is None
    assert logical_address_for("tcam", 0x1011) == 0x1011


def test_the_address_is_an_int_not_a_string(current):
    """0x1011, "1011" and 4113 must not become three catalog join keys."""
    current(vehicle(ecu("TCAM", doip={"logical_address": "4113"})))

    assert doip_facet_for("tcam").logical_address == 4113


def test_the_addresses_declare_themselves_as_hex():
    """An editor built from the schema would otherwise ask for 4113.

    Nothing downstream may guess this from the field name -- the facet that
    knows the convention is the one that states it.
    """
    schema = DoipFacet.model_json_schema()["properties"]

    assert schema["logical_address"]["format"] == "hex"
    assert schema["tester_address"]["format"] == "hex"
    assert "format" not in schema["port"], "a TCP port is written in decimal"


def test_the_address_is_still_required():
    """Attaching display metadata must not quietly hand it a default."""
    with pytest.raises(ValidationError):
        DoipFacet()


def test_the_facet_carries_no_secret():
    """PINs stay in ClassifiedInfo/Env_Mgr; a JSON column is not a secret store."""
    assert not any("pin" in name or "secret" in name for name in DoipFacet.model_fields)


def test_a_lookup_failure_never_raises(monkeypatch):
    """Address resolution sits in hardware paths; it must degrade, not explode."""
    import iotsploit_django.adapters.django.target_models as target_models

    def boom():
        raise RuntimeError("database is gone")

    monkeypatch.setattr(target_models.TargetManager, "get_instance", staticmethod(boom))

    assert logical_address_for("tcam", 0x1011) == 0x1011
    assert mod.doip_facet_for("tcam") is None
