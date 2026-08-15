"""GET /api/get_facet_schemas/.

This is what lets a client render typed, labelled fields for a facet it has no
compiled knowledge of. A key missing from the response is not an error: it
means no loaded plugin owns it, and the client must show it read-only rather
than dropping it.
"""

from __future__ import annotations

import json
import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.test import RequestFactory  # noqa: E402

from iotsploit_core.domain.facet import Facet, FacetRegistry  # noqa: E402
from iotsploit_django.view_handlers.target_views import get_facet_schemas  # noqa: E402

pytestmark = pytest.mark.contract


def fetch():
    response = get_facet_schemas(RequestFactory().get("/api/get_facet_schemas/"))
    assert response.status_code == 200
    return json.loads(response.content)


def test_the_registered_doip_facet_is_published():
    body = fetch()

    assert body["status"] == "success"
    assert "doip" in body["facet_schemas"]


def test_a_schema_carries_types_and_required_fields():
    """Enough for a client to build a form: which fields, what type, which
    are mandatory."""
    schema = fetch()["facet_schemas"]["doip"]

    assert schema["properties"]["logical_address"]["type"] == "integer"
    assert schema["properties"]["port"]["default"] == 13400
    assert "logical_address" in schema["required"]


def test_the_registered_can_facet_is_published():
    """Nothing consumes the CAN facet yet, so only the app's ready() hook
    imports it. Without that, a stored facet loads as RawFacet and the editor
    shows a target's frames as an unrecognised blob."""
    assert "can" in fetch()["facet_schemas"]


def test_a_list_of_frames_is_published_as_an_array():
    """What the editor keys off to show the frames instead of handing them a
    text box that would overwrite them."""
    schema = fetch()["facet_schemas"]["can"]

    assert schema["properties"]["messages"]["type"] == "array"
    assert "bus_id" in schema["required"]


def test_a_newly_registered_facet_appears_without_a_restart():
    """Registration happens at plugin load, so the endpoint must read the
    registry live rather than a snapshot taken at import."""

    class BenchFacet(Facet):
        rack: str = ""

    FacetRegistry.register("bench_probe", BenchFacet)
    try:
        assert "bench_probe" in fetch()["facet_schemas"]
    finally:
        FacetRegistry.unregister("bench_probe")

    assert "bench_probe" not in fetch()["facet_schemas"]


def test_the_response_is_json_serializable():
    """JsonResponse would raise on a schema containing a non-JSON type."""
    body = fetch()

    json.dumps(body["facet_schemas"])
