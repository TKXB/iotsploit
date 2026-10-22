"""GET /api/list_targets/ and GET /api/get_target/<id>/.

The listing used to return every target in full. On the VW MQB fixture that is
~254 kB of CAN signals on the wire, for a table that shows a name and a count.
These tests hold the split in place: the listing is a projection, the detail
endpoint is the whole object, and neither pretends to be the other.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.test import RequestFactory  # noqa: E402

from iotsploit_core.domain.summary import SUMMARY_FLAG  # noqa: E402
from iotsploit_django.adapters.django.target_models import TargetManager  # noqa: E402
from iotsploit_django.view_handlers import target_views  # noqa: E402

pytestmark = pytest.mark.contract

FIXTURE = Path(__file__).resolve().parents[2] / "conf" / "vw_golf_mqb_target.json"


@pytest.fixture
def golf():
    """The real MQB target, as ``get_all_targets`` would hand it over."""
    if not FIXTURE.exists():
        pytest.skip(f"{FIXTURE} is not present")
    return json.loads(FIXTURE.read_text())["targets"][0]


@pytest.fixture
def stored(monkeypatch, golf):
    """Stand in for the database with one known target."""

    class FakeManager:
        @staticmethod
        def get_all_targets():
            return [golf]

        @staticmethod
        def get_target(target_id):
            # The detail endpoint asks for one target by id rather than
            # scanning every row. Both are answered from the same single
            # stored target so listing and detail cannot disagree.
            return golf if target_id == golf["target_id"] else None

    monkeypatch.setattr(target_views.TargetManager, "get_instance", lambda: FakeManager)
    return golf


def listing():
    response = target_views.list_targets(RequestFactory().get("/api/list_targets/"))
    assert response.status_code == 200
    return json.loads(response.content)


def detail(target_id):
    return target_views.get_target(
        RequestFactory().get(f"/api/get_target/{target_id}/"), target_id
    )


def test_the_listing_is_flagged_as_a_projection(stored):
    """A caller has to be able to refuse to write this back."""
    row = listing()["targets"][0]

    assert row[SUMMARY_FLAG] is True


def test_the_listing_drops_the_frames(stored):
    gateway = next(c for c in listing()["targets"][0]["components"] if c["component_id"] == "c_gateway_mqb")

    assert "messages" not in gateway["facets"]["can"]
    assert gateway["facet_sizes"]["can"]["messages"] == 35


def test_the_listing_keeps_what_a_table_shows(stored):
    row = listing()["targets"][0]

    assert row["name"] == "VW Golf (MQB powertrain)"
    assert row["type"] == "vehicle"
    assert row["component_count"] == 19
    assert row["bus_count"] == 1
    assert row["edge_count"] == 19


def test_the_listing_is_an_order_of_magnitude_smaller(stored, golf):
    """The number this endpoint change exists for.

    673 kB is the fixture *file*, which is indented. Compact on the wire the
    same target is ~254 kB, and that is what a client paid for every listing
    before this projection existed. The row it gets now is ~6 kB: a factor of
    about 40, floored here at 30 so a few more scalar fields do not fail it.
    """
    before = len(json.dumps(golf, separators=(",", ":")))
    after = len(json.dumps(listing()["targets"][0], separators=(",", ":")))

    assert before > 250_000
    assert after * 30 < before


def test_an_empty_database_still_answers(monkeypatch):
    class Empty:
        @staticmethod
        def get_all_targets():
            return []

    monkeypatch.setattr(target_views.TargetManager, "get_instance", lambda: Empty)

    body = listing()
    assert body["status"] == "success" and body["targets"] == []


def test_the_detail_endpoint_returns_every_signal(stored):
    body = json.loads(detail("vw_golf_mqb").content)
    gateway = next(c for c in body["target"]["components"] if c["component_id"] == "c_gateway_mqb")

    assert len(gateway["facets"]["can"]["messages"]) == 35
    assert sum(len(m["signals"]) for m in gateway["facets"]["can"]["messages"]) == 619


def test_the_detail_endpoint_is_not_flagged_as_a_summary(stored):
    """Nothing was dropped, so nothing may claim it was."""
    body = json.loads(detail("vw_golf_mqb").content)

    assert SUMMARY_FLAG not in body["target"]


def test_an_unknown_target_is_a_404_not_an_empty_success(stored):
    response = detail("no_such_target")

    assert response.status_code == 404


def test_get_target_by_id_has_no_side_effect_on_the_current_selection():
    """The single-target read used to be a linear scan of every target in the
    database. Now it is one query -- and, more importantly, one that cannot
    change which target other clients see, because the plugin endpoint relies
    on exactly that when a caller names its own target.
    """
    manager = TargetManager.get_instance()
    before = manager.get_current_target()

    unknown = manager.get_target("definitely-not-a-target")

    assert unknown is None
    assert manager.get_current_target() is before


def test_get_target_never_returns_the_settings_pseudo_target():
    """__settings__ stores the current-target selection, not a target. It is
    excluded from listing, and asking for it by name must not be a way around
    that."""
    assert TargetManager.get_instance().get_target("__settings__") is None
