"""Transport-neutral execution of one durable plugin run."""

from __future__ import annotations

import json
import logging

from django.db import close_old_connections

from iotsploit_core.core.interaction_binding import bind_interaction
from iotsploit_core.ports.interaction import InteractionCancelled, InteractionTimeout
from iotsploit_django.adapters.django.interaction import service
from iotsploit_django.adapters.django.interaction.adapter import DurableInteractionAdapter
from iotsploit_django.adapters.django.interaction.log_stream import stream_logs
from iotsploit_django.adapters.django.target_models import TargetManager

logger = logging.getLogger(__name__)

INTERACTIVE_QUEUE = "interactive"
STREAMING_QUEUE = "streaming"
STANDARD_QUEUE = "celery"


def execution_queue(plugin_name, parameters, *, interactive=True):
    """Choose one existing workload queue from request semantics."""
    if plugin_name != "CAN Live Capture":
        return INTERACTIVE_QUEUE if interactive else STANDARD_QUEUE

    request = (parameters or {}).get("request")
    if isinstance(request, str):
        try:
            request = json.loads(request)
        except json.JSONDecodeError:
            return INTERACTIVE_QUEUE if interactive else STANDARD_QUEUE
    if isinstance(request, dict):
        if request.get("mode") == "monitor":
            return STREAMING_QUEUE
        if request.get("mode", "capture") == "capture":
            return STANDARD_QUEUE
    return INTERACTIVE_QUEUE if interactive else STANDARD_QUEUE


def configure_execution_runtime():
    """Wire process-local stream adapters before plugin execution."""
    from iotsploit_django.composition_root.core_container import configure_stream_backend

    configure_stream_backend()


def run_execution(
    execution_id,
    plugin_name,
    *,
    target=None,
    parameters=None,
    celery_task_id="",
):
    """Run a plugin and own every durable state transition around it."""
    close_old_connections()

    try:
        service.mark_running(execution_id, celery_task_id=celery_task_id)
        from iotsploit_django.composition_root.core_container import build_exploit_plugin_manager

        configure_execution_runtime()
        manager = build_exploit_plugin_manager()
        if target and isinstance(target, dict):
            target = TargetManager.get_instance().create_target_instance(target)

        port = DurableInteractionAdapter(execution_id)
        with bind_interaction(port), stream_logs(execution_id):
            raw_result, provenance = manager.run_plugin_in_process(
                plugin_name, target, parameters
            )

        result = _as_dict(raw_result)
        result.update(provenance or {})
        if result.get("reason") == "unavailable":
            service.mark_failed(execution_id, result["message"], reason="unavailable")
            return result
        service.mark_completed(execution_id, result)
        return result
    except InteractionTimeout as exc:
        service.mark_failed(execution_id, str(exc), reason="timeout")
        return {"status": "error", "message": str(exc), "reason": "timeout"}
    except InteractionCancelled as exc:
        logger.info("Execution %s cancelled: %s", execution_id, exc)
        return {"status": "cancelled", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a run failure is durable result state
        logger.error("Execution %s failed: %s", execution_id, exc, exc_info=True)
        service.mark_failed(execution_id, str(exc))
        return {"status": "error", "message": str(exc)}
    finally:
        close_old_connections()


def _as_dict(raw_result) -> dict:
    if raw_result is None:
        return {"status": "success", "message": "Completed", "data": None}
    if isinstance(raw_result, dict):
        return raw_result
    return {
        "status": "success" if getattr(raw_result, "success", True) else "error",
        "message": str(getattr(raw_result, "message", "Completed")),
        "data": getattr(raw_result, "data", None),
        "progress": getattr(raw_result, "progress", 100),
    }
