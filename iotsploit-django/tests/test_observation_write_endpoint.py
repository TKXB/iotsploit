"""POST /api/record_observations/.

The endpoint exists so a caller that observed something itself -- an agent, a
tool run on the bench -- can make that durable. The property being defended is
that its facts stay distinguishable from a plugin's measurement and cannot
overwrite one, which is why most of these tests are about the source.
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
from iotsploit_core.domain.observation import Fact, ObservationScope, ScanStatus  # noqa: E402
from iotsploit_django.adapters.django.observation_models import (  # noqa: E402
    ScanRunDBModel,
    enable_sqlite_foreign_keys,
    initialize_observation_schema,
)
from iotsploit_django.adapters.django.observation_repository import ObservationRepository  # noqa: E402
from iotsploit_django.adapters.sqlalchemy.database import create_sqlalchemy_db  # noqa: E402
from iotsploit_django.view_handlers.observation_views import (  # noqa: E402
    AGENT_SOURCE_PREFIX,
    get_current_observations,
    record_observations,
)

pytestmark = pytest.mark.contract

TARGET = "write_endpoint_target"

PORT_22 = {
    "protocol": "tcp",
    "subject_kind": "port",
    "subject_id": "22",
    "observed_property": "open",
    "value": {"banner": "OpenSSH 8.9"},
}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Point the view at a throwaway database rather than the developer's."""
    db = create_sqlalchemy_db(f"sqlite:///{tmp_path / 'observations.sqlite3'}")
    enable_sqlite_foreign_keys(db.engine)
    initialize_observation_schema(db)
    instance = ObservationRepository(db)
    monkeypatch.setattr(repo_module, "ObservationRepository", lambda *a, **k: instance)
    return instance


def post(body, *, as_json=True):
    request = RequestFactory().post(
        "/api/record_observations/",
        data=json.dumps(body) if as_json else body,
        content_type="application/json",
    )
    response = record_observations(request)
    return response.status_code, json.loads(response.content)


def current(target_id=TARGET):
    request = RequestFactory().get("/api/get_current_observations/", {"target_id": target_id})
    return json.loads(get_current_observations(request).content)["observations"]


def scans(repo, target_id=TARGET):
    session = repo._session_factory()
    try:
        return session.query(ScanRunDBModel).filter(ScanRunDBModel.target_id == target_id).all()
    finally:
        session.close()


def test_get_is_not_a_way_to_write(repo):
    response = record_observations(RequestFactory().get("/api/record_observations/"))

    assert response.status_code == 405


def test_a_missing_target_id_is_rejected(repo):
    status, _ = post({"agent": "claude", "scope_key": "tcp:22", "facts": [PORT_22]})

    assert status == 400


def test_a_missing_scope_key_is_rejected(repo):
    """is_complete is a claim about the scope, so there has to be one."""
    status, body = post({"target_id": TARGET, "agent": "claude", "facts": [PORT_22]})

    assert status == 400
    assert "scope_key" in body["error"]


def test_a_caller_supplied_source_is_refused_not_ignored(repo):
    """Accepting the field and overriding it would report a success that lied."""
    status, body = post({
        "target_id": TARGET,
        "source": "can_sniff",
        "scope_key": "tcp:22",
        "facts": [PORT_22],
    })

    assert status == 400
    assert "source is assigned by the server" in body["error"]
    assert scans(repo) == []


def test_the_source_is_namespaced_so_a_plugin_cannot_be_impersonated(repo):
    """The whole point: an agent naming itself after a sniffer still reads as an agent."""
    status, body = post({
        "target_id": TARGET,
        "agent": "can_sniff",
        "scope_key": "tcp:22",
        "facts": [PORT_22],
    })

    assert status == 200
    assert body["source"] == f"{AGENT_SOURCE_PREFIX}can_sniff"
    assert current()[0]["source"] == f"{AGENT_SOURCE_PREFIX}can_sniff"


def test_an_awkward_label_is_sanitised_rather_than_rejected(repo):
    """Losing a real observation over punctuation would be the worse failure."""
    _, body = post({
        "target_id": TARGET,
        "agent": "Claude Code (opus)",
        "scope_key": "tcp:22",
        "facts": [PORT_22],
    })

    assert body["source"] == f"{AGENT_SOURCE_PREFIX}claude-code-opus"


def test_an_absent_label_still_produces_a_usable_source(repo):
    _, body = post({"target_id": TARGET, "scope_key": "tcp:22", "facts": [PORT_22]})

    assert body["source"] == f"{AGENT_SOURCE_PREFIX}unknown"


def test_a_recorded_fact_comes_back_with_its_identity_and_provenance(repo):
    post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "tcp:22,80,443",
        "component_id": "c_gateway",
        "facts": [PORT_22],
    })

    record = current()[0]
    assert record["protocol"] == "tcp"
    assert record["subject_kind"] == "port"
    assert record["subject_id"] == "22"
    assert record["observed_property"] == "open"
    assert record["value"] == {"banner": "OpenSSH 8.9"}
    assert record["display_key"] == "tcp.port.22.open"
    assert record["scope_key"] == "tcp:22,80,443"
    assert record["component_id"] == "c_gateway"


def test_a_malformed_fact_leaves_no_trace_at_all(repo):
    """Validated before the scan opens, so there is no half-written scan to explain."""
    status, body = post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "tcp:22",
        "facts": [{"protocol": "tcp", "subject_kind": "port", "observed_property": "open"}],
    })

    assert status == 400
    assert "facts[0]" in body["error"]
    assert scans(repo) == []


def test_a_fact_about_the_target_itself_needs_no_subject_id(repo):
    status, _ = post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "host:reachability",
        "facts": [{
            "protocol": "ip",
            "subject_kind": "self",
            "observed_property": "reachable",
            "value": True,
        }],
    })

    assert status == 200
    assert current()[0]["subject_id"] is None


def test_a_repeated_fact_is_named_rather_than_hitting_the_unique_index(repo):
    status, body = post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "tcp:22",
        "facts": [PORT_22, dict(PORT_22, value={"banner": "something else"})],
    })

    assert status == 400
    assert "tcp.port.22.open" in body["error"]
    assert scans(repo) == []


def test_finding_nothing_is_a_result(repo):
    """An empty complete snapshot is how "this is not exposed" gets recorded."""
    status, body = post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "tcp:1-1024",
        "facts": [],
    })

    assert status == 200
    assert body["facts_recorded"] == 0
    assert scans(repo)[0].status == ScanStatus.SUCCEEDED.value


def test_a_partial_scan_is_kept_but_does_not_define_current_state(repo):
    """is_complete=False is the honest answer to "I only spot-checked"."""
    status, body = post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "tcp:1-65535",
        "is_complete": False,
        "facts": [PORT_22],
    })

    assert status == 200
    assert body["facts_recorded"] == 1
    assert scans(repo)[0].status == ScanStatus.SUCCEEDED.value
    assert current() == []


def test_an_agent_snapshot_cannot_clear_a_plugin_s_facts(repo):
    """source is one of the comparable scope fields, so the two never collide.

    This is what makes is_complete safe to accept from a caller at all: the
    blast radius of a wrong completeness claim is the caller's own history.
    """
    scan = repo.start_scans(
        run_id="plugin_run",
        target_id=TARGET,
        source="nmap_scan",
        scopes=[ObservationScope(scope_key="tcp:22,80,443")],
    )[0]
    repo.complete_scan(scan.scan_id, [Fact(**PORT_22)])

    post({
        "target_id": TARGET,
        "agent": "claude",
        "scope_key": "tcp:22,80,443",
        "is_complete": True,
        "facts": [],
    })

    sources = {record["source"] for record in current()}
    assert "nmap_scan" in sources


def test_an_agent_does_replace_its_own_previous_snapshot(repo):
    """Same source, same scope: the newer complete scan is the current one."""
    body = {"target_id": TARGET, "agent": "claude", "scope_key": "tcp:22,80,443"}
    post(dict(body, facts=[PORT_22]))
    post(dict(body, facts=[dict(PORT_22, subject_id="80")]))

    assert [record["subject_id"] for record in current()] == ["80"]


def test_invalid_json_is_a_400_not_a_500(repo):
    request = RequestFactory().post(
        "/api/record_observations/", data="{not json", content_type="application/json"
    )

    assert record_observations(request).status_code == 400
