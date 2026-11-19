"""GET /api/get_current_observations/.

Provenance is the point: a caller must be able to see which tool said what, or
two tools reporting on the same subject become indistinguishable.
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

import iotsploit_django.adapters.django.observation_repository as repo_module  # noqa: E402
from iotsploit_core.domain.observation import Fact, ObservationScope  # noqa: E402
from iotsploit_django.adapters.django.observation_models import (  # noqa: E402
    ObservationDBModel,
    ScanRunDBModel,
    enable_sqlite_foreign_keys,
    initialize_observation_schema,
)
from iotsploit_django.adapters.django.observation_repository import ObservationRepository  # noqa: E402
from iotsploit_django.adapters.sqlalchemy.database import create_sqlalchemy_db  # noqa: E402
from iotsploit_django.view_handlers.observation_views import (  # noqa: E402
    delete_observation_facts,
    get_current_observations,
)

pytestmark = pytest.mark.contract

TARGET = "endpoint_test_target"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Point the view at a throwaway database rather than the developer's."""
    db = create_sqlalchemy_db(f"sqlite:///{tmp_path / 'observations.sqlite3'}")
    enable_sqlite_foreign_keys(db.engine)
    initialize_observation_schema(db)
    instance = ObservationRepository(db)
    monkeypatch.setattr(repo_module, "ObservationRepository", lambda *a, **k: instance)
    return instance


@pytest.fixture
def seeded(repo):
    scans = repo.start_scans(
        run_id="endpoint_test_run",
        target_id=TARGET,
        source="doip_did_enum",
        scopes=[ObservationScope(scope_key="did:identification", component_id="c_tcam")],
    )
    repo.complete_scan(
        scans[0].scan_id,
        [
            Fact(
                protocol="uds",
                subject_kind="did",
                subject_id="F190",
                observed_property="response",
                value="LB37622Z0PX000001",
            )
        ],
    )
    return repo


def fetch(target_id=TARGET):
    request = RequestFactory().get("/api/get_current_observations/", {"target_id": target_id})
    response = get_current_observations(request)
    return response.status_code, json.loads(response.content)


def test_a_missing_target_id_is_rejected(repo):
    response = get_current_observations(RequestFactory().get("/api/get_current_observations/"))

    assert response.status_code == 400


def test_an_unknown_target_returns_an_empty_list_not_an_error(repo):
    """"Nothing scanned yet" is a normal state, not a failure."""
    status, body = fetch("no_such_target_at_all")

    assert status == 200
    assert body["observations"] == []


def test_a_fact_is_returned_with_its_identity_columns(seeded):
    status, body = fetch()
    record = next(r for r in body["observations"] if r["subject_id"] == "F190")

    assert status == 200
    assert record["protocol"] == "uds"
    assert record["subject_kind"] == "did"
    assert record["observed_property"] == "response"
    assert record["value"] == "LB37622Z0PX000001"
    assert record["display_key"] == "uds.did.F190.response"


def test_a_fact_carries_its_provenance(seeded):
    """Without these, two tools reporting the same subject are indistinguishable."""
    record = next(r for r in fetch()[1]["observations"] if r["subject_id"] == "F190")

    assert record["source"] == "doip_did_enum"
    assert record["scope_key"] == "did:identification"
    assert record["component_id"] == "c_tcam"
    assert record["scan_id"] and record["observed_at"]


def test_the_response_is_json_serializable(seeded):
    """observed_at is a datetime; JsonResponse would raise if it leaked through."""
    json.dumps(fetch()[1])


def delete_facts(fact_ids, target_id=TARGET):
    request = RequestFactory().post(
        "/api/delete_observation_facts/",
        data=json.dumps({"target_id": target_id, "fact_ids": fact_ids}),
        content_type="application/json",
    )
    response = delete_observation_facts(request)
    return response.status_code, json.loads(response.content)


def complete_scan(repo, source, target_id=TARGET):
    scan_id = repo.start_scan(
        target_id=target_id,
        source=source,
        scope_key="can:powertrain",
    )
    repo.complete_scan(
        scan_id,
        [Fact(protocol="can", subject_kind="message", subject_id="120", observed_property="seen", value=True)],
    )
    return scan_id


def test_delete_is_scoped_to_the_confirmed_fact_and_target(repo):
    first = complete_scan(repo, "capture_a")
    other = complete_scan(repo, "capture_b")
    outside = complete_scan(repo, "capture_a", "other_target")
    selected = next(record["fact_id"] for record in fetch()[1]["observations"] if record["scan_id"] == first)
    foreign = fetch("other_target")[1]["observations"][0]["fact_id"]

    status, body = delete_facts([selected, foreign])

    assert status == 200
    assert body["deleted"] == 1
    assert [record["scan_id"] for record in body["observations"]] == [other]
    assert [record["scan_id"] for record in fetch("other_target")[1]["observations"]] == [outside]
    assert delete_facts([selected])[1]["deleted"] == 0


def test_clear_retains_empty_current_scans_so_historical_facts_stay_hidden(repo):
    historical = complete_scan(repo, "capture_a")
    current = complete_scan(repo, "capture_a")
    complete_scan(repo, "capture_b")
    ids = [record["fact_id"] for record in fetch()[1]["observations"]]

    status, body = delete_facts(ids)

    assert status == 200
    assert body["deleted"] == 2
    assert body["observations"] == fetch()[1]["observations"] == []
    with repo._session_factory() as session:
        assert session.get(ScanRunDBModel, current) is not None
        assert session.query(ObservationDBModel).filter_by(scan_id=historical).count() == 1


def test_clear_preserves_a_scan_completed_during_confirmation(repo):
    superseded = complete_scan(repo, "capture_a")
    complete_scan(repo, "capture_b")
    ids = [record["fact_id"] for record in fetch()[1]["observations"]]
    new_scan = complete_scan(repo, "capture_a")

    status, body = delete_facts(ids)

    assert status == 200
    assert body["deleted"] == 1
    assert [record["scan_id"] for record in body["observations"]] == [new_scan]
    with repo._session_factory() as session:
        assert session.query(ObservationDBModel).filter_by(scan_id=superseded).count() == 1
