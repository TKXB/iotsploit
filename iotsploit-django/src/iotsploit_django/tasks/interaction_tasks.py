"""Celery adapter for durable plugin executions."""

from __future__ import annotations

from celery import shared_task

from iotsploit_django.adapters.django.interaction.runtime import (
    INTERACTIVE_QUEUE,
    STANDARD_QUEUE,
    STREAMING_QUEUE,
    run_execution,
)

__all__ = [
    "INTERACTIVE_QUEUE",
    "STANDARD_QUEUE",
    "STREAMING_QUEUE",
    "run_execution_task",
]


@shared_task(bind=True, queue=INTERACTIVE_QUEUE, max_retries=0)
def run_execution_task(self, execution_id, plugin_name, target=None, parameters=None):
    """Thin Celery adapter around the shared execution owner."""
    return run_execution(
        execution_id,
        plugin_name,
        target=target,
        parameters=parameters,
        celery_task_id=self.request.id or "",
    )
