"""State transitions for interactive plugin execution.

Every change to an execution or an input request goes through here, so the
durable adapter, the HTTP endpoints, and the sweep cannot drift apart on what
"answered" or "cancelled" means. The adapter translates between the port and
these functions; it does not own the lifecycle.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from iotsploit_core.ports.interaction import Prompt, coerce_answer
from iotsploit_django.adapters.django.interaction.events import emit
from iotsploit_django.adapters.django.interaction.models import (
    ExecutionStatus,
    InputRequest,
    PluginExecution,
    RequestStatus,
)

logger = logging.getLogger(__name__)

# How long past its deadline a pending request may sit before the sweep decides
# its worker is gone. Generous, because a live worker always resolves its own
# prompt first and a false positive kills a real run.
SWEEP_GRACE = timedelta(seconds=60)


class AnswerOutcome:
    ACCEPTED = "accepted"
    CONFLICT = "conflict"
    INVALID = "invalid"
    NOT_FOUND = "not_found"


# ── Executions ───────────────────────────────────────────────────────

def create_execution(plugin_name, *, target=None, parameters=None,
                     operator=None, plugin_version="") -> PluginExecution:
    return PluginExecution.objects.create(
        plugin_name=plugin_name,
        plugin_version=plugin_version or "",
        target_snapshot=_snapshot(target),
        parameters=parameters or {},
        operator=operator,
    )


def _snapshot(target) -> dict | None:
    """A serialisable copy of the target as it was when the run started."""
    if target is None:
        return None
    if isinstance(target, dict):
        return target
    if hasattr(target, "get_info"):
        try:
            return target.get_info()
        except Exception:  # noqa: BLE001 - a bad snapshot must not stop a run
            logger.warning("Could not snapshot target for execution", exc_info=True)
    return None


def mark_running(execution_id, *, celery_task_id="") -> None:
    updates = {"status": ExecutionStatus.RUNNING, "started_at": timezone.now()}
    if celery_task_id:
        updates["celery_task_id"] = celery_task_id
    PluginExecution.objects.filter(execution_id=execution_id).update(**updates)
    emit(execution_id, "execution_started", {})


def mark_completed(execution_id, result: dict | None) -> None:
    _finish(execution_id, ExecutionStatus.COMPLETED, {"result": result})
    emit(execution_id, "completed", {"result": result})


def mark_failed(execution_id, message: str, *, reason: str = "error") -> None:
    error = {"message": message, "reason": reason}
    _finish(execution_id, ExecutionStatus.FAILED, {"error": error})
    emit(execution_id, "failed", error)


def _finish(execution_id, status, extra: dict) -> None:
    with transaction.atomic():
        execution = _locked(execution_id)
        if execution is None or execution.is_terminal:
            return
        execution.status = status
        execution.completed_at = timezone.now()
        for field, value in extra.items():
            setattr(execution, field, value)
        execution.save()
        _close_pending(execution, RequestStatus.CANCELLED)


def cancel_execution(execution_id, *, reason: str = "operator") -> bool:
    """Ask a run to stop. Returns False if it had already finished."""
    with transaction.atomic():
        execution = _locked(execution_id)
        if execution is None or execution.is_terminal:
            return False
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = timezone.now()
        execution.error = {"reason": reason}
        execution.save()
        _close_pending(execution, RequestStatus.CANCELLED)
    emit(execution_id, "cancelled", {"reason": reason})
    return True


def _locked(execution_id) -> PluginExecution | None:
    return PluginExecution.objects.select_for_update().filter(
        execution_id=execution_id).first()


def _close_pending(execution: PluginExecution, status) -> None:
    execution.input_requests.filter(status=RequestStatus.PENDING).update(status=status)


# ── Input requests ───────────────────────────────────────────────────

def create_request(execution_id, prompt: Prompt) -> InputRequest:
    request = InputRequest.objects.create(
        execution_id=execution_id,
        kind=prompt.kind,
        title=prompt.title,
        description=prompt.description or "",
        validation=prompt.validation_schema(),
        default=prompt.default,
        expires_at=timezone.now() + timedelta(seconds=prompt.timeout),
    )
    PluginExecution.objects.filter(execution_id=execution_id).update(
        status=ExecutionStatus.WAITING_INPUT)
    emit(execution_id, "input_required", wire_prompt(request))
    return request


def wire_prompt(request: InputRequest) -> dict[str, Any]:
    """The prompt as clients receive it (plan A.5)."""
    return {
        "request_id": str(request.request_id),
        "execution_id": str(request.execution_id),
        "kind": request.kind,
        "title": request.title,
        "description": request.description or None,
        "default": request.default,
        "created_at": _iso(request.created_at),
        "expires_at": _iso(request.expires_at),
        "validation": request.validation or {},
    }


def record_answer(execution_id, request_id, raw_value, *, operator=None):
    """Accept an answer if the request is still open.

    Returns ``(outcome, detail)``. The transition from pending to answered is
    atomic, so of two clients answering at once exactly one wins.
    """
    with transaction.atomic():
        request = InputRequest.objects.select_for_update().filter(
            request_id=request_id, execution_id=execution_id).first()
        if request is None:
            return AnswerOutcome.NOT_FOUND, None

        if request.status != RequestStatus.PENDING:
            return AnswerOutcome.CONFLICT, _conflict_reason(request)

        if request.is_expired:
            request.status = RequestStatus.EXPIRED
            request.save(update_fields=["status"])
            return AnswerOutcome.CONFLICT, "expired"

        try:
            value = coerce_answer(_prompt_from(request), raw_value)
        except Exception as exc:  # InteractionInvalid
            return AnswerOutcome.INVALID, str(exc)

        request.status = RequestStatus.ANSWERED
        request.answer_value = value
        request.answered_at = timezone.now()
        request.answered_by = operator
        request.save(update_fields=[
            "status", "answer_value", "answered_at", "answered_by"])

    emit(execution_id, "input_answered",
         {"request_id": str(request_id), "value": value})
    return AnswerOutcome.ACCEPTED, value


def _conflict_reason(request: InputRequest) -> str:
    return {
        RequestStatus.ANSWERED: "already_answered",
        RequestStatus.EXPIRED: "expired",
        RequestStatus.CANCELLED: "cancelled",
    }.get(request.status, "closed")


def expire_request(request_id) -> None:
    """Close a request whose deadline passed with nobody answering."""
    with transaction.atomic():
        request = InputRequest.objects.select_for_update().filter(
            request_id=request_id, status=RequestStatus.PENDING).first()
        if request is None:
            return          # answered in the meantime; the answer wins
        request.status = RequestStatus.EXPIRED
        request.save(update_fields=["status"])
        execution_id = request.execution_id
    emit(execution_id, "input_expired", {"request_id": str(request_id)})


def _prompt_from(request: InputRequest) -> Prompt:
    """Rebuild the prompt from what was stored, for validating an answer."""
    validation = request.validation or {}
    choices = [c["value"] for c in validation.get("choices", [])]
    return Prompt(
        kind=request.kind,
        title=request.title,
        choices=tuple(choices),
        required=validation.get("required", True),
        min_value=validation.get("min"),
        max_value=validation.get("max"),
        max_length=validation.get("max_length"),
        min_selected=validation.get("min_selected"),
    )


# ── Recovery ─────────────────────────────────────────────────────────

def sweep_stranded(now=None) -> int:
    """Finish executions whose worker went away while a prompt was open.

    The prompt's own deadline is the liveness signal: a live worker always
    resolves its own request first, so anything still pending well past
    `expires_at` has nobody behind it.
    """
    now = now or timezone.now()
    cutoff = now - SWEEP_GRACE
    stranded = PluginExecution.objects.filter(
        status=ExecutionStatus.WAITING_INPUT,
        input_requests__status=RequestStatus.PENDING,
        input_requests__expires_at__lt=cutoff,
    ).distinct()

    count = 0
    for execution in stranded:
        with transaction.atomic():
            locked = _locked(execution.execution_id)
            if locked is None or locked.is_terminal:
                continue
            locked.status = ExecutionStatus.EXPIRED
            locked.completed_at = now
            locked.error = {"reason": "worker_lost"}
            locked.save()
            _close_pending(locked, RequestStatus.CANCELLED)
        emit(execution.execution_id, "expired", {"reason": "worker_lost"})
        logger.warning("Swept stranded execution %s", execution.execution_id)
        count += 1
    return count


def _iso(value) -> str | None:
    return value.isoformat() if value else None
