"""The HTTP surface Flutter answers prompts through.

Answering is a mutating operation, so it has one path with one set of
validation and one conflict story. These pin the status codes the client
branches on.
"""

from __future__ import annotations

import json
import os
import uuid

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.test import Client  # noqa: E402

from iotsploit_core.ports.interaction import Prompt  # noqa: E402
from iotsploit_django.adapters.django.interaction import service  # noqa: E402
from iotsploit_django.adapters.django.interaction.models import (  # noqa: E402
    ExecutionStatus,
    RequestStatus,
)

pytestmark = [pytest.mark.django, pytest.mark.contract]


@pytest.fixture(autouse=True)
def _use_test_database(db):
    """Every test in this module talks to the throwaway database."""


@pytest.fixture(autouse=True)
def _no_events(monkeypatch):
    monkeypatch.setattr(service, "emit", lambda *a, **k: None)


@pytest.fixture
def client():
    yield Client()


def an_execution():
    return service.create_execution("Interactive Demo", target={"ip": "10.0.0.1"})


def a_request(execution):
    return service.create_request(
        execution.execution_id,
        Prompt(kind="single_choice", title="Session",
               choices=("default", "extended")),
    )


def answer_url(execution, request):
    return (f"/api/plugin-executions/{execution.execution_id}"
            f"/inputs/{request.request_id}/answer/")


def post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type="application/json")


# ── State ────────────────────────────────────────────────────────────

def test_state_carries_the_open_prompt_so_a_reload_can_restore_it():
    execution = an_execution()
    a_request(execution)

    client = Client()
    response = client.get(f"/api/plugin-executions/{execution.execution_id}/")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == ExecutionStatus.WAITING_INPUT
    assert body["pending_request"]["title"] == "Session"
    assert body["pending_request"]["validation"]["choices"][0]["value"] == "default"


def test_state_lists_what_was_already_answered():
    execution = an_execution()
    request = a_request(execution)
    service.record_answer(execution.execution_id, request.request_id, "extended")

    body = Client().get(f"/api/plugin-executions/{execution.execution_id}/").json()

    assert body["pending_request"] is None
    assert body["answered_requests"][0]["value"] == "extended"


def test_an_unknown_execution_is_404(client):
    response = client.get(f"/api/plugin-executions/{uuid.uuid4()}/")
    assert response.status_code == 404


# ── Answering ────────────────────────────────────────────────────────

def test_a_valid_answer_is_accepted(client):
    execution = an_execution()
    request = a_request(execution)

    response = post(client, answer_url(execution, request), {"value": "extended"})

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    request.refresh_from_db()
    assert request.answer_value == "extended"


def test_a_second_answer_is_409_already_answered(client):
    execution = an_execution()
    request = a_request(execution)
    post(client, answer_url(execution, request), {"value": "default"})

    response = post(client, answer_url(execution, request), {"value": "extended"})

    assert response.status_code == 409
    assert response.json()["reason"] == "already_answered"


def test_an_invalid_value_is_400_and_leaves_the_prompt_open(client):
    execution = an_execution()
    request = a_request(execution)

    response = post(client, answer_url(execution, request), {"value": "nope"})

    assert response.status_code == 400
    assert response.json()["status"] == "invalid"
    request.refresh_from_db()
    assert request.status == RequestStatus.PENDING


def test_a_missing_value_is_400(client):
    execution = an_execution()
    request = a_request(execution)

    response = post(client, answer_url(execution, request), {})

    assert response.status_code == 400


def test_a_request_id_from_another_execution_is_404(client):
    execution, other = an_execution(), an_execution()
    request = a_request(execution)

    url = (f"/api/plugin-executions/{other.execution_id}"
           f"/inputs/{request.request_id}/answer/")

    assert post(client, url, {"value": "default"}).status_code == 404


def test_get_is_rejected_on_the_answer_route(client):
    execution = an_execution()
    request = a_request(execution)
    assert client.get(answer_url(execution, request)).status_code == 405


# ── Cancelling ───────────────────────────────────────────────────────

def test_cancelling_reports_that_it_started(client):
    execution = an_execution()
    a_request(execution)

    response = post(client, f"/api/plugin-executions/{execution.execution_id}/cancel/", {})

    assert response.status_code == 200
    assert response.json() == {"status": "cancelling"}
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.CANCELLED


def test_cancelling_a_finished_run_is_409(client):
    execution = an_execution()
    service.mark_completed(execution.execution_id, {})

    response = post(client, f"/api/plugin-executions/{execution.execution_id}/cancel/", {})

    assert response.status_code == 409


def test_cancelling_an_unknown_execution_is_404(client):
    response = post(client, f"/api/plugin-executions/{uuid.uuid4()}/cancel/", {})
    assert response.status_code == 404


# ── Finding an open prompt without having watched ────────────────────

def test_pending_lists_the_open_question(client):
    execution = an_execution()
    a_request(execution)

    body = client.get("/api/plugin-executions/pending/").json()

    assert len(body["pending"]) == 1
    assert body["pending"][0]["execution_id"] == str(execution.execution_id)


def test_pending_is_empty_once_answered(client):
    execution = an_execution()
    request = a_request(execution)
    service.record_answer(execution.execution_id, request.request_id, "default")

    assert Client().get("/api/plugin-executions/pending/").json()["pending"] == []
