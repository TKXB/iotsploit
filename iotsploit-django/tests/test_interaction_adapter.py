"""The durable adapter: ask through the database, wait for an answer.

Polling is the whole mechanism, so these drive the real loop with a short
interval. The answer is recorded on the same connection the loop reads from --
a second thread would open its own connection, and the in-memory test database
is not shared between them.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_core.ports.interaction import (  # noqa: E402
    InteractionCancelled,
    InteractionTimeout,
    Prompt,
)
from iotsploit_django.adapters.django.interaction import adapter as adapter_module  # noqa: E402
from iotsploit_django.adapters.django.interaction import service  # noqa: E402
from iotsploit_django.adapters.django.interaction.adapter import (  # noqa: E402
    DurableInteractionAdapter,
)
from iotsploit_django.adapters.django.interaction.models import (  # noqa: E402
    ExecutionStatus,
    InputRequest,
    PluginExecution,
    RequestStatus,
)

pytestmark = [pytest.mark.django, pytest.mark.integration]

FAST = 0.01


@pytest.fixture(autouse=True)
def _use_test_database(db):
    """Every test in this module talks to the throwaway database."""


@pytest.fixture(autouse=True)
def _no_events(monkeypatch):
    monkeypatch.setattr(service, "emit", lambda *a, **k: None)


def an_execution():
    return service.create_execution("Interactive Demo", target={})


def a_prompt(**kw):
    kw.setdefault("kind", "single_choice")
    kw.setdefault("title", "Session")
    kw.setdefault("choices", ("default", "extended"))
    return Prompt(**kw)


def once_asked(monkeypatch, action):
    """Run `action(request)` the moment the adapter raises its prompt.

    Stands in for the operator: by the time the loop takes its first look, the
    answer (or the cancellation) is already in the database, exactly as it
    would be when it arrives from another process.
    """
    real = service.create_request

    def wrapper(execution_id, prompt):
        request = real(execution_id, prompt)
        action(request)
        return request

    monkeypatch.setattr(adapter_module.service, "create_request", wrapper)


def answers(monkeypatch, value):
    once_asked(monkeypatch, lambda r: service.record_answer(
        r.execution_id, r.request_id, value))


def test_an_answer_recorded_elsewhere_comes_back_typed(monkeypatch):
    execution = an_execution()
    answers(monkeypatch, "extended")
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    assert port.request(a_prompt()) == "extended"


def test_the_execution_goes_back_to_running_once_answered(monkeypatch):
    execution = an_execution()
    answers(monkeypatch, "default")
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    port.request(a_prompt())

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.RUNNING


def test_the_execution_is_marked_waiting_while_a_prompt_is_open(monkeypatch):
    execution = an_execution()
    seen = {}

    def note(request):
        execution.refresh_from_db()
        seen["status"] = execution.status
        service.record_answer(request.execution_id, request.request_id, "default")

    once_asked(monkeypatch, note)
    DurableInteractionAdapter(execution.execution_id,
                              poll_seconds=FAST).request(a_prompt())

    assert seen["status"] == ExecutionStatus.WAITING_INPUT


def test_two_prompts_in_a_row_each_get_their_own_answer(monkeypatch):
    execution = an_execution()
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    answers(monkeypatch, "extended")
    first = port.request(a_prompt())

    answers(monkeypatch, 42)
    second = port.request(Prompt(kind="integer", title="DIDs"))

    assert (first, second) == ("extended", 42)


def test_the_sugar_reaches_the_durable_path(monkeypatch):
    execution = an_execution()
    answers(monkeypatch, True)
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    assert port.confirm("Send the reset?") is True


def test_a_prompt_nobody_answers_times_out():
    execution = an_execution()
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    with pytest.raises(InteractionTimeout, match="within"):
        port.request(a_prompt(timeout=0.05))

    assert InputRequest.objects.filter(
        execution_id=execution.execution_id,
        status=RequestStatus.EXPIRED).exists()


def test_cancelling_the_run_wakes_the_waiting_worker(monkeypatch):
    execution = an_execution()
    once_asked(monkeypatch,
               lambda r: service.cancel_execution(r.execution_id))
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    with pytest.raises(InteractionCancelled, match="cancelled"):
        port.request(a_prompt(timeout=30))


def test_a_deleted_execution_does_not_leave_the_worker_spinning(monkeypatch):
    execution = an_execution()
    once_asked(monkeypatch, lambda r: PluginExecution.objects.filter(
        execution_id=r.execution_id).delete())
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    with pytest.raises(InteractionCancelled, match="no longer exists"):
        port.request(a_prompt(timeout=30))


def test_an_expired_request_stops_the_worker_even_without_its_own_deadline(monkeypatch):
    """The sweep closes the request; the worker must notice and give up."""
    execution = an_execution()
    once_asked(monkeypatch, lambda r: InputRequest.objects.filter(
        request_id=r.request_id).update(status=RequestStatus.EXPIRED))
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    with pytest.raises(InteractionTimeout):
        port.request(a_prompt(timeout=30))


def test_check_cancelled_raises_after_a_cancel():
    execution = an_execution()
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)

    port.check_cancelled()                      # nothing wrong yet
    service.cancel_execution(execution.execution_id)
    port._last_cancel_check = 0.0               # bypass the rate limit

    with pytest.raises(InteractionCancelled):
        port.check_cancelled()


def test_check_cancelled_is_rate_limited_so_tight_loops_are_cheap():
    execution = an_execution()
    port = DurableInteractionAdapter(execution.execution_id, poll_seconds=FAST)
    port.check_cancelled()

    service.cancel_execution(execution.execution_id)
    port.check_cancelled()      # too soon to look again; must not raise
