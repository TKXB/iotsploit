"""POST /api/create_target/ and /api/edit_target/ against the whole model.

The write contract used to stop at components: buses and edges were dropped
without a word, so a client could post a complete network, be told it was
created, and get back a bag of components with no topology. These tests send
what a client actually builds and check what survives -- and check that a
payload the model refuses comes back saying why, rather than as a bare 500.
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
from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402

pytestmark = pytest.mark.contract

TARGET_ID = "write_contract_target"


def network(**overrides):
    """A target that is a network, not a bag of components."""
    payload = {
        "target_id": TARGET_ID,
        "name": "Bench Router",
        "type": "router",
        "status": "active",
        "properties": {"note": "x"},
        "components": [
            {
                "component_id": "c_soc",
                "name": "SoC",
                "type": "generic",
                "status": "active",
                "facets": {"ssh": {"port": 22, "user": "root"}},
                "properties": {},
            }
        ],
        "buses": [
            {"bus_id": "b_lan", "name": "LAN", "type": "ethernet", "properties": {}}
        ],
        "edges": [
            {
                "source": "c_soc",
                "target": "b_lan",
                "relation": "bus_member",
                "properties": {"role": "uplink"},
            }
        ],
    }
    payload.update(overrides)
    return payload


class FakeManager:
    """Stands in for the singleton, which is bound to the real database."""

    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.saved = None

    def get_all_targets(self):
        return self.existing

    # The views hydrate through the real code path, so validation is real.
    create_target_instance = TargetManager.create_target_instance
    _hydrate_target = staticmethod(TargetManager._hydrate_target)

    def save_target(self, instance):
        self.saved = json.loads(instance.model_dump_json())

    def update_target(self, data):
        self.saved = data
        return True


@pytest.fixture
def manager(monkeypatch):
    def install(existing=None):
        fake = FakeManager(existing)
        monkeypatch.setattr(views.TargetManager, "get_instance", staticmethod(lambda: fake))
        return fake

    return install


def create(payload):
    request = RequestFactory().post(
        "/api/create_target/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    return views.create_target(request)


def edit(updates, target_id=TARGET_ID):
    request = RequestFactory().post(
        "/api/edit_target/",
        data=json.dumps({"target_id": target_id, "updates": updates}),
        content_type="application/json",
    )
    return views.edit_target(request)


# ── create ──────────────────────────────────────────────────────────


def test_create_stores_the_topology_it_was_given(manager):
    fake = manager()

    response = create(network())

    assert json.loads(response.content)["status"] == "success"
    assert [b["bus_id"] for b in fake.saved["buses"]] == ["b_lan"]
    assert [e["relation"] for e in fake.saved["edges"]] == ["bus_member"]


def test_create_keeps_what_an_edge_records_about_itself(manager):
    fake = manager()

    create(network())

    assert fake.saved["edges"][0]["properties"] == {"role": "uplink"}


def test_create_without_topology_still_works(manager):
    """Every client that predates this sends no buses and no edges."""
    fake = manager()
    payload = network()
    del payload["buses"]
    del payload["edges"]

    assert json.loads(create(payload).content)["status"] == "success"
    assert fake.saved["buses"] == []
    assert fake.saved["edges"] == []


def test_an_edge_pointing_at_nothing_is_a_400_that_says_so(manager):
    """The model refuses it. The caller has to be told why, or it cannot
    correct itself -- this used to surface as a bare 500."""
    manager()

    response = create(network(edges=[
        {"source": "c_ghost", "target": "b_lan", "relation": "bus_member", "properties": {}}
    ]))

    assert response.status_code == 400
    body = json.loads(response.content)["error"]
    assert "c_ghost" in body


def test_a_duplicate_id_is_still_refused(manager):
    manager(existing=[{"target_id": TARGET_ID}])

    assert create(network()).status_code == 400


def test_missing_required_fields_are_still_refused(manager):
    manager()
    payload = network()
    del payload["name"]

    assert create(payload).status_code == 400


# ── edit ────────────────────────────────────────────────────────────


@pytest.fixture
def stored(manager):
    return manager(existing=[network()])


def test_edit_replaces_the_topology(stored):
    response = edit({
        "buses": [
            {"bus_id": "b_lan", "name": "LAN", "type": "ethernet", "properties": {}},
            {"bus_id": "b_wan", "name": "WAN", "type": "ethernet", "properties": {}},
        ],
        "edges": [
            {"source": "c_soc", "target": "b_wan", "relation": "connects", "properties": {}},
        ],
    })

    assert json.loads(response.content)["status"] == "success"
    assert [b["bus_id"] for b in stored.saved["buses"]] == ["b_lan", "b_wan"]
    assert stored.saved["edges"][0]["relation"] == "connects"


def test_edit_rejects_an_edge_the_update_orphaned(stored):
    """Deleting the component an edge names is the commonest way to get here."""
    response = edit({"components": []})

    assert response.status_code == 400
    assert "c_soc" in json.loads(response.content)["error"]


def test_edit_leaves_topology_alone_when_it_is_not_mentioned(stored):
    edit({"name": "Renamed"})

    assert stored.saved["name"] == "Renamed"
    assert [b["bus_id"] for b in stored.saved["buses"]] == ["b_lan"]
    assert len(stored.saved["edges"]) == 1


def test_the_whitelist_is_still_a_whitelist(stored):
    edit({"target_id": "renamed", "created_at": "1999-01-01"})

    assert stored.saved["target_id"] == TARGET_ID
    assert "created_at" not in stored.saved
