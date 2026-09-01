from __future__ import annotations

from typing import Any

from iotsploit_django.adapters.django.interaction import service
from iotsploit_django.adapters.django.interaction.runtime import execution_queue


class CeleryTaskRunner:
    """TaskRunner implementation backed by iotsploit_django Celery task."""

    def submit(
        self,
        plugin_name: str,
        target: dict | None,
        parameters: dict,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]:
        # Import the selected Celery app before any @shared_task module so the
        # web process publishes to the configured Redis broker, not Celery's
        # implicit AMQP default.
        from iotsploit_django.tasks.celery_app import app as _celery_app  # noqa: F401
        from iotsploit_django.tasks.interaction_tasks import run_execution_task

        interactive = bool((context or {}).get("interactive"))
        execution = service.create_execution(
            plugin_name, target=target, parameters=parameters
        )
        queue = execution_queue(plugin_name, parameters, interactive=interactive)
        try:
            task = run_execution_task.apply_async(
                args=[str(execution.execution_id), plugin_name],
                kwargs={
                    "target": execution.target_snapshot,
                    "parameters": parameters,
                },
                queue=queue,
            )
        except Exception as exc:
            service.mark_failed(
                execution.execution_id, str(exc), reason="dispatch_failed"
            )
            raise
        service.record_celery_task_id(execution.execution_id, task.id)
        return {
            "execution_type": "interactive" if interactive else "async",
            "execution_id": str(execution.execution_id),
            "task_id": str(execution.execution_id),
        }
