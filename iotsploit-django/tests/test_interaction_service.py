"""Execution and input-request state transitions.

The atomic answer is the load-bearing part: two clients racing on one prompt
must produce exactly one winner, and a worker must never lose an answer that
was recorded.
"""

from __future__ import annotations

import os
from datetime import timedelta

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.utils import timezone  # noqa: E402

from iotsploit_core.ports.interaction import Prompt  # noqa: E402
from iotsploit_django.adapters.django.interaction import service  # noqa: E402
from iotsploit_django.adapters.django.interaction.models import (  # noqa: E402
    ExecutionStatus,
    InputRequest,
    RequestStatus,
)

pytestmark = [pytest.mark.django, pytest.mark.integration]

Outcome = service.AnswerOutcome


@pytest.fixture(autouse=True)
def _use_test_database(db):
    """Every test in this module talks to the throwaway database."""


@pytest.fixture(autouse=True)
def _no_events(monkeypatch):
    """Events need a channel layer; the transitions under test do not."""
    monkeypatch.setattr(service, "emit", lambda *a, **k: None)


def an_execution(**kwargs):
    return service.create_execution(
        kwargs.pop("plugin_name", "Interactive Demo"),
        target=kwargs.pop("target", {"ip": "192.168.10.4"}),
        parameters=kwargs.pop("parameters", {}),
        **kwargs,
    )


def a_prompt(**kwargs):
    kwargs.setdefault("kind", "single_choice")
    kwargs.setdefault("title", "Select the session")
    kwargs.setdefault("choices", ("default", "extended"))
    return Prompt(**kwargs)


# ── Executions ───────────────────────────────────────────────────────

def test_a_new_execution_is_queued_and_snapshots_its_target():
    execution = an_execution(target={"ip": "10.0.0.1", "vin": "LB37"})
    assert execution.status == ExecutionStatus.QUEUED
    assert execution.target_snapshot["vin"] == "LB37"


def test_a_target_object_is_snapshotted_through_get_info():
    class Target:
        def get_info(self):
            return {"name": "ZXD"}

    assert an_execution(target=Target()).target_snapshot == {"name": "ZXD"}


def test_a_target_that_cannot_be_snapshotted_does_not_stop_the_run():
    class Hostile:
        def get_info(self):
            raise RuntimeError("nope")

    assert an_execution(target=Hostile()).target_snapshot is None


def test_completing_records_the_result():
    execution = an_execution()
    service.mark_completed(execution.execution_id, {"message": "done"})
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.result == {"message": "done"}
    assert execution.completed_at is not None


def test_a_finished_execution_is_not_reopened_by_a_late_failure():
    execution = an_execution()
    service.mark_completed(execution.execution_id, {"message": "done"})
    service.mark_failed(execution.execution_id, "too late")
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.COMPLETED


# ── Prompts ──────────────────────────────────────────────────────────

def test_raising_a_prompt_moves_the_execution_to_waiting():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())
    execution.refresh_from_db()

    assert execution.status == ExecutionStatus.WAITING_INPUT
    assert request.status == RequestStatus.PENDING
    assert request.validation["choices"][0]["value"] == "default"


def test_the_wire_prompt_carries_what_a_client_needs_to_render():
    execution = an_execution()
    request = service.create_request(
        execution.execution_id,
        a_prompt(description="Pick one", default="default"),
    )
    wire = service.wire_prompt(request)

    assert wire["kind"] == "single_choice"
    assert wire["description"] == "Pick one"
    assert wire["default"] == "default"
    assert wire["expires_at"] is not None
    assert set(wire) >= {"request_id", "execution_id", "title", "validation"}


# ── Answers ──────────────────────────────────────────────────────────

def test_a_valid_answer_is_accepted_and_stored():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())

    outcome, value = service.record_answer(
        execution.execution_id, request.request_id, "extended")

    assert (outcome, value) == (Outcome.ACCEPTED, "extended")
    request.refresh_from_db()
    assert request.status == RequestStatus.ANSWERED
    assert request.answer_value == "extended"


def test_the_second_client_to_answer_gets_a_conflict():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())

    first, _ = service.record_answer(
        execution.execution_id, request.request_id, "default")
    second, reason = service.record_answer(
        execution.execution_id, request.request_id, "extended")

    assert first == Outcome.ACCEPTED
    assert (second, reason) == (Outcome.CONFLICT, "already_answered")
    request.refresh_from_db()
    assert request.answer_value == "default"        # the first answer wins


def test_an_answer_off_the_choice_list_is_rejected():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())

    outcome, detail = service.record_answer(
        execution.execution_id, request.request_id, "programming")

    assert outcome == Outcome.INVALID
    assert "not one of" in detail
    request.refresh_from_db()
    assert request.status == RequestStatus.PENDING   # still answerable


def test_stored_numeric_bounds_are_enforced_on_the_way_back_in():
    execution = an_execution()
    request = service.create_request(
        execution.execution_id,
        Prompt(kind="integer", title="DIDs", min_value=1, max_value=100),
    )

    assert service.record_answer(
        execution.execution_id, request.request_id, 500)[0] == Outcome.INVALID
    assert service.record_answer(
        execution.execution_id, request.request_id, "50") == (Outcome.ACCEPTED, 50)


def test_an_answer_for_the_wrong_execution_is_not_found():
    execution, other = an_execution(), an_execution()
    request = service.create_request(execution.execution_id, a_prompt())

    outcome, _ = service.record_answer(
        other.execution_id, request.request_id, "default")

    assert outcome == Outcome.NOT_FOUND


def test_answering_after_the_deadline_is_a_conflict():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())
    InputRequest.objects.filter(request_id=request.request_id).update(
        expires_at=timezone.now() - timedelta(seconds=1))

    outcome, reason = service.record_answer(
        execution.execution_id, request.request_id, "default")

    assert (outcome, reason) == (Outcome.CONFLICT, "expired")


# ── Expiry and cancellation ──────────────────────────────────────────

def test_expiring_a_request_that_was_just_answered_leaves_the_answer_alone():
    """The race the sweep must not lose."""
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())
    service.record_answer(execution.execution_id, request.request_id, "extended")

    service.expire_request(request.request_id)

    request.refresh_from_db()
    assert request.status == RequestStatus.ANSWERED
    assert request.answer_value == "extended"


def test_cancelling_closes_the_open_prompt():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())

    assert service.cancel_execution(execution.execution_id) is True

    execution.refresh_from_db()
    request.refresh_from_db()
    assert execution.status == ExecutionStatus.CANCELLED
    assert request.status == RequestStatus.CANCELLED


def test_cancelling_a_finished_run_reports_that_it_was_too_late():
    execution = an_execution()
    service.mark_completed(execution.execution_id, {})
    assert service.cancel_execution(execution.execution_id) is False


# ── Sweep ────────────────────────────────────────────────────────────

def test_the_sweep_finishes_a_run_whose_worker_went_away():
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())
    InputRequest.objects.filter(request_id=request.request_id).update(
        expires_at=timezone.now() - service.SWEEP_GRACE - timedelta(seconds=5))

    assert service.sweep_stranded() == 1

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.EXPIRED
    assert execution.error["reason"] == "worker_lost"


def test_the_sweep_leaves_a_prompt_inside_its_grace_period_alone():
    """A live worker resolves its own prompt; the grace stops false positives."""
    execution = an_execution()
    request = service.create_request(execution.execution_id, a_prompt())
    InputRequest.objects.filter(request_id=request.request_id).update(
        expires_at=timezone.now() - timedelta(seconds=1))

    assert service.sweep_stranded() == 0
    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.WAITING_INPUT


def test_the_sweep_ignores_runs_that_are_not_waiting():
    execution = an_execution()
    service.mark_running(execution.execution_id)
    assert service.sweep_stranded() == 0
