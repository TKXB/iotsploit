"""Durable execution and input-request records.

The partial unique constraint is the load-bearing part: it is what makes "one
question at a time per run" a database guarantee rather than a convention the
adapter has to remember.
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

from django.db import IntegrityError, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from iotsploit_django.adapters.django.interaction.models import (  # noqa: E402
    ExecutionStatus,
    InputRequest,
    PluginExecution,
    RequestStatus,
)

pytestmark = [pytest.mark.django, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _use_test_database(db):
    """Every test in this module talks to the throwaway database."""


def make_execution(**kwargs):
    return PluginExecution.objects.create(
        plugin_name=kwargs.pop("plugin_name", "uds_session_probe"),
        target_snapshot=kwargs.pop("target_snapshot", {"ip": "192.168.10.4"}),
        parameters=kwargs.pop("parameters", {}),
        **kwargs,
    )


def make_request(execution, **kwargs):
    return InputRequest.objects.create(
        execution=execution,
        kind=kwargs.pop("kind", "single_choice"),
        title=kwargs.pop("title", "Select the diagnostic session"),
        validation=kwargs.pop("validation", {"choices": []}),
        expires_at=kwargs.pop("expires_at", timezone.now() + timedelta(minutes=5)),
        **kwargs,
    )


def test_execution_starts_queued_with_a_generated_id():
    execution = make_execution()
    assert execution.status == ExecutionStatus.QUEUED
    assert execution.execution_id is not None
    assert execution.is_terminal is False


def test_target_is_a_snapshot_so_a_later_switch_cannot_rewrite_history():
    execution = make_execution(target_snapshot={"ip": "192.168.10.4", "vin": "LB37"})
    execution.refresh_from_db()
    assert execution.target_snapshot["vin"] == "LB37"


def test_only_one_request_can_be_pending_per_execution():
    execution = make_execution()
    make_request(execution)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_request(execution, title="A second question")


def test_a_new_request_is_allowed_once_the_previous_one_is_answered():
    execution = make_execution()
    first = make_request(execution)

    first.status = RequestStatus.ANSWERED
    first.answered_at = timezone.now()
    first.answer_value = "extended"
    first.save()

    second = make_request(execution, title="Security access")
    assert execution.input_requests.count() == 2
    assert execution.pending_request() == second


def test_two_executions_may_each_have_a_pending_request():
    """The constraint is per execution, not global."""
    first, second = make_execution(), make_execution()
    make_request(first)
    make_request(second)
    assert InputRequest.objects.filter(status=RequestStatus.PENDING).count() == 2


def test_pending_request_is_none_when_nothing_is_open():
    execution = make_execution()
    assert execution.pending_request() is None


def test_is_expired_tracks_the_deadline():
    execution = make_execution()
    live = make_request(execution)
    assert live.is_expired is False

    live.status = RequestStatus.EXPIRED
    live.save()
    stale = make_request(execution, expires_at=timezone.now() - timedelta(seconds=1))
    assert stale.is_expired is True


def test_terminal_statuses_are_recognised():
    execution = make_execution()
    for status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
                   ExecutionStatus.CANCELLED, ExecutionStatus.EXPIRED):
        execution.status = status
        assert execution.is_terminal is True

    for status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING,
                   ExecutionStatus.WAITING_INPUT):
        execution.status = status
        assert execution.is_terminal is False


def test_requests_are_removed_with_their_execution():
    execution = make_execution()
    make_request(execution)
    execution.delete()
    assert InputRequest.objects.count() == 0


def test_operator_is_optional_while_authentication_is_pending():
    execution = make_execution()
    assert execution.operator is None
    request = make_request(execution)
    assert request.answered_by is None
