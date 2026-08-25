"""Celery tasks for executions that can stop and ask the operator something.

These run on their own queue at concurrency 1. Waiting for an answer holds a
worker slot without using CPU, so isolating them keeps ordinary plugin runs
moving, and the concurrency of one means exactly one execution can be waiting
on a prompt at a time -- which is what lets the Control Panel show a single
unambiguous question.
"""

from __future__ import annotations

from celery import shared_task
from celery.utils.log import get_task_logger

from iotsploit_core.core.interaction_binding import bind_interaction
from iotsploit_core.ports.interaction import (
    InteractionCancelled,
    InteractionTimeout,
)
from iotsploit_django.adapters.django.interaction import service
from iotsploit_django.adapters.django.interaction.adapter import DurableInteractionAdapter
from iotsploit_django.adapters.django.interaction.log_stream import stream_logs
from iotsploit_django.adapters.django.target_models import TargetManager
from iotsploit_django.composition_root.wiring import get_exploit_plugin_manager

logger = get_task_logger(__name__)

INTERACTIVE_QUEUE = "interactive"
STREAMING_QUEUE = "streaming"


@shared_task(bind=True, queue=INTERACTIVE_QUEUE, max_retries=0)
def run_execution_task(self, execution_id, plugin_name, target=None, parameters=None):
    """Run one plugin with a durable interaction port bound to it.

    No retries: a retried run would re-ask questions the operator has already
    answered, and the answers belong to the execution that asked them.
    """
    service.mark_running(execution_id, celery_task_id=self.request.id or "")

    try:
        manager = get_exploit_plugin_manager(use_celery=False)

        if target and isinstance(target, dict):
            target = TargetManager.get_instance().create_target_instance(target)

        port = DurableInteractionAdapter(execution_id)
        # stream_logs is what puts a plugin's own account of the run into the
        # transcript, next to the prompts it raised. Without it the only place
        # a plugin could show anything was the next prompt's description.
        with bind_interaction(port), stream_logs(execution_id):
            raw_result, provenance = manager.run_plugin_in_process(
                plugin_name, target, parameters
            )

        result = _as_dict(raw_result)
        result.update(provenance or {})
        service.mark_completed(execution_id, result)
        return result

    except InteractionTimeout as exc:
        service.mark_failed(execution_id, str(exc), reason="timeout")
        return {"status": "error", "message": str(exc), "reason": "timeout"}

    except InteractionCancelled as exc:
        # cancel_execution already recorded the terminal state and told the
        # client; this only unwinds the worker.
        logger.info("Execution %s cancelled: %s", execution_id, exc)
        return {"status": "cancelled", "message": str(exc)}

    except Exception as exc:  # noqa: BLE001 - the run's failure is the result
        logger.error("Execution %s failed: %s", execution_id, exc, exc_info=True)
        service.mark_failed(execution_id, str(exc))
        return {"status": "error", "message": str(exc)}


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


@shared_task
def sweep_stranded_executions():
    """Finish runs whose worker went away while a prompt was open."""
    swept = service.sweep_stranded()
    if swept:
        logger.warning("Swept %d stranded execution(s)", swept)
    return swept
