"""Saving a component from the UI, all the way to a typed facet.

This is the path that has already lost data once: the edit dialog replaces a
stored component wholesale, so anything the request drops is gone. These tests
send exactly what the dialog builds and check what survives.
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

import iotsploit_django.view_handlers.target_views as views  # noqa: E402
from iotsploit_core.domain.target import Vehicle  # noqa: E402
from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402
from iotsploit_django.tools.doip_facet import DoipFacet  # noqa: E402

pytestmark = pytest.mark.contract

TARGET_ID = "facet_edit_target"


def stored_component(**overrides):
    component = {
        "component_id": "c_tcam",
        "name": "TCAM",
        "type": "ecu",
        "status": "active",
        "properties": {},
        "facets": {},
    }
    component.update(overrides)
    return component


class FakeManager:
    """Stands in for the singleton, which is bound to the real database.

    Hydration is the real thing, not a stub: edit_target builds the target
    through it to decide whether the payload is valid at all, so a fake that
    skipped it would pass writes the model would refuse.
    """

    def __init__(self, target):
        self.target = target
        self.saved = None

    def get_all_targets(self):
        return [self.target]

    create_target_instance = TargetManager.create_target_instance
    _hydrate_target = staticmethod(TargetManager._hydrate_target)

    def update_target(self, data):
        self.saved = data
        return True


@pytest.fixture
def manager(monkeypatch):
    def install(component):
        fake = FakeManager(
            {
                "target_id": TARGET_ID,
                "name": "Zeekr 001",
                "type": "vehicle",
                "status": "active",
                "properties": {},
                "components": [component],
                "interfaces": [],
            }
        )
        monkeypatch.setattr(views.TargetManager, "get_instance", staticmethod(lambda: fake))
        return fake

    return install


def post(components):
    return post_updates({"components": components})


def post_updates(updates):
    request = RequestFactory().post(
        "/api/edit_target/",
        data=json.dumps({"target_id": TARGET_ID, "updates": updates}),
        content_type="application/json",
    )
    return views.edit_target(request)


def hydrate(saved):
    """Through the same code the request path uses, minus the database."""
    return TargetManager._hydrate_target(saved, Vehicle)


def test_a_new_facet_reaches_the_database(manager):
    fake = manager(stored_component())

    response = post([stored_component(facets={"doip": {"logical_address": 4113, "port": 13400}})])

    assert response.status_code == 200
    assert fake.saved["components"][0]["facets"]["doip"]["logical_address"] == 4113


def test_a_saved_facet_hydrates_into_its_registered_type(manager):
    """A dict in a JSON column is only useful if it comes back as a DoipFacet."""
    fake = manager(stored_component())

    post([stored_component(facets={"doip": {"logical_address": 4113, "host": "198.18.34.1"}})])
    component = hydrate(fake.saved).components[0]

    facet = component.facet("doip")
    assert isinstance(facet, DoipFacet)
    assert facet.logical_address == 4113
    assert facet.host == "198.18.34.1"
    assert facet.tester_address == 0x0E80, "an unsent field takes the facet's default"


def test_an_existing_facet_can_be_changed(manager):
    fake = manager(stored_component(facets={"doip": {"logical_address": 4113}}))

    post([stored_component(facets={"doip": {"logical_address": 0x1201}})])

    assert hydrate(fake.saved).components[0].facet("doip").logical_address == 0x1201


def test_removing_the_last_facet_survives_the_save(manager):
    """An empty dict must mean "none", not "unchanged"."""
    fake = manager(stored_component(facets={"doip": {"logical_address": 4113}}))

    post([stored_component(facets={})])

    assert fake.saved["components"][0]["facets"] == {}
    assert hydrate(fake.saved).components[0].facet("doip") is None


def test_a_facet_is_not_demoted_into_properties(manager):
    """`facets` is a real field; a hydration that missed it would hide it here."""
    fake = manager(stored_component())

    post([stored_component(facets={"doip": {"logical_address": 4113}})])
    component = hydrate(fake.saved).components[0]

    assert component.properties == {}
    assert "doip" in component.facets


def test_an_untouched_component_keeps_its_facet(manager):
    """Editing only the name must not be a way to lose protocol config."""
    fake = manager(stored_component(facets={"doip": {"logical_address": 4113}}))

    post([stored_component(name="TCAM-2", facets={"doip": {"logical_address": 4113}})])

    assert hydrate(fake.saved).components[0].facet("doip").logical_address == 4113


def test_the_type_the_dialog_sends_is_the_type_that_is_stored(manager):
    """It was dropped, and the request said success anyway.

    The edit dialog puts `type` in every payload it builds and create_target
    already accepts one, so a user could change a target from vehicle to
    router, be told it had been updated, and find it unchanged.
    """
    fake = manager(stored_component())

    response = post_updates({"type": "router"})

    assert json.loads(response.content)["status"] == "success"
    assert fake.saved["type"] == "router"


def test_a_field_the_contract_does_not_accept_is_still_ignored(manager):
    """The whitelist is the contract; widening it for `type` did not open it."""
    fake = manager(stored_component())

    post_updates({"target_id": "renamed", "created_at": "1999-01-01"})

    assert fake.saved["target_id"] == TARGET_ID
    assert "created_at" not in fake.saved


def test_the_rest_of_the_target_survives_a_type_change(manager):
    """Changing the type must not take the components with it."""
    fake = manager(stored_component(name="TCAM"))

    post_updates({"type": "generic"})

    assert fake.saved["type"] == "generic"
    assert [c["name"] for c in fake.saved["components"]] == ["TCAM"]
