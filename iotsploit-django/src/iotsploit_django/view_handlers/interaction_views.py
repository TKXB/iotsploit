"""HTTP endpoints for interactive plugin executions.

Answers and cancellation are mutating operations, so they go over HTTP rather
than the WebSocket: there is one place to add authentication, one place to
validate, and one audited path.

Authentication does not exist in this project yet -- here or anywhere else in
the API. These views resolve an operator where one is available and record it,
so adding a decorator is the only remaining change; see "Prerequisite:
Authentication" in the plan.
"""

from __future__ import annotations

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from iotsploit_django.adapters.django.interaction import service
from iotsploit_django.adapters.django.interaction.models import (
    InputRequest,
    PluginExecution,
    RequestStatus,
)

logger = logging.getLogger(__name__)


def _operator(request):
    """The signed-in operator, once there is such a thing."""
    user = getattr(request, "user", None)
    return user if getattr(user, "is_authenticated", False) else None


def execution_state(execution_id) -> dict | None:
    """Everything a client needs to render a run, including an open prompt.

    Shared with the WebSocket consumer so a reconnecting client sees exactly
    what a fresh GET would return.
    """
    execution = PluginExecution.objects.filter(execution_id=execution_id).first()
    if execution is None:
        return None

    pending = execution.pending_request()
    answered = [
        {
            "request_id": str(r.request_id),
            "kind": r.kind,
            "title": r.title,
            "answered_at": r.answered_at.isoformat() if r.answered_at else None,
            "value": r.answer_value,
        }
        for r in execution.input_requests.filter(status=RequestStatus.ANSWERED)
    ]

    return {
        "execution_id": str(execution.execution_id),
        "plugin_name": execution.plugin_name,
        "status": execution.status,
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": (
            execution.completed_at.isoformat() if execution.completed_at else None
        ),
        "pending_request": service.wire_prompt(pending) if pending else None,
        "answered_requests": answered,
        "result": execution.result,
        "error": execution.error,
    }


@csrf_exempt
def get_execution(request, execution_id):
    """GET /api/plugin-executions/<execution_id>/"""
    if request.method != "GET":
        return JsonResponse({"status": "error", "message": "Only GET is allowed"},
                            status=405)

    state = execution_state(execution_id)
    if state is None:
        return JsonResponse({"status": "not_found"}, status=404)
    return JsonResponse(state)


@csrf_exempt
def answer_input_request(request, execution_id, request_id):
    """POST /api/plugin-executions/<execution_id>/inputs/<request_id>/answer/"""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST is allowed"},
                            status=405)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "invalid", "errors": "Body is not JSON."},
                            status=400)

    if "value" not in body:
        return JsonResponse({"status": "invalid", "errors": "No value supplied."},
                            status=400)

    outcome, detail = service.record_answer(
        execution_id, request_id, body["value"], operator=_operator(request)
    )

    if outcome == service.AnswerOutcome.ACCEPTED:
        return JsonResponse({"status": "accepted"})
    if outcome == service.AnswerOutcome.NOT_FOUND:
        return JsonResponse({"status": "not_found"}, status=404)
    if outcome == service.AnswerOutcome.INVALID:
        return JsonResponse({"status": "invalid", "errors": detail}, status=400)
    return JsonResponse({"status": "conflict", "reason": detail}, status=409)


@csrf_exempt
def cancel_execution(request, execution_id):
    """POST /api/plugin-executions/<execution_id>/cancel/

    Cancellation is asynchronous. The run is marked terminal here and any open
    prompt is closed, which is what wakes the waiting worker; the final event
    arrives on the execution socket.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST is allowed"},
                            status=405)

    if not PluginExecution.objects.filter(execution_id=execution_id).exists():
        return JsonResponse({"status": "not_found"}, status=404)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}

    cancelled = service.cancel_execution(
        execution_id, reason=body.get("reason") or "operator"
    )
    if not cancelled:
        return JsonResponse({"status": "conflict", "reason": "already_finished"},
                            status=409)
    return JsonResponse({"status": "cancelling"})


@csrf_exempt
def list_pending_requests(request):
    """GET /api/plugin-executions/pending/

    Which run, if any, is currently waiting on someone. The interactive queue
    runs at concurrency 1, so this is at most one -- it lets a client that was
    not watching find the open question after a reload.
    """
    if request.method != "GET":
        return JsonResponse({"status": "error", "message": "Only GET is allowed"},
                            status=405)

    pending = (
        InputRequest.objects.filter(status=RequestStatus.PENDING)
        .select_related("execution")
        .order_by("created_at")
    )
    return JsonResponse({
        "status": "success",
        "pending": [service.wire_prompt(r) for r in pending],
    })
