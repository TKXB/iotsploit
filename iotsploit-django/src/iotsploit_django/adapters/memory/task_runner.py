from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import threading
from typing import Any

from django.conf import settings

from iotsploit_django.adapters.django.interaction import service
from iotsploit_django.adapters.django.interaction.runtime import (
    INTERACTIVE_QUEUE,
    STANDARD_QUEUE,
    STREAMING_QUEUE,
    execution_queue,
    run_execution,
)

logger = logging.getLogger(__name__)

_executors = None
_executors_lock = threading.Lock()
_reconciled = False


def _local_executors():
    global _executors
    if _executors is None:
        with _executors_lock:
            if _executors is None:
                _executors = {
                    STANDARD_QUEUE: ThreadPoolExecutor(
                        max_workers=settings.IOTSPLOIT_LOCAL_STANDARD_WORKERS,
                        thread_name_prefix="iotsploit-standard",
                    ),
                    INTERACTIVE_QUEUE: ThreadPoolExecutor(
                        max_workers=1, thread_name_prefix="iotsploit-interactive"
                    ),
                    STREAMING_QUEUE: ThreadPoolExecutor(
                        max_workers=1, thread_name_prefix="iotsploit-streaming"
                    ),
                }
    return _executors


class InProcessTaskRunner:
    """Durable local TaskRunner backed by process-local worker threads."""

    def submit(
        self,
        plugin_name: str,
        target: dict | None,
        parameters: dict,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]:
        global _reconciled
        if not _reconciled:
            with _executors_lock:
                if not _reconciled:
                    service.fail_orphaned_local_executions()
                    _reconciled = True

        execution = service.create_execution(
            plugin_name, target=target, parameters=parameters
        )
        interactive = bool((context or {}).get("interactive"))
        queue = execution_queue(plugin_name, parameters, interactive=interactive)
        try:
            _local_executors()[queue].submit(
                run_execution,
                str(execution.execution_id),
                plugin_name,
                target=execution.target_snapshot,
                parameters=parameters,
            )
        except Exception as exc:
            service.mark_failed(
                execution.execution_id, str(exc), reason="dispatch_failed"
            )
            raise
        logger.info(
            "Queued local execution %s for %s on %s",
            execution.execution_id,
            plugin_name,
            queue,
        )
        return {
            "execution_type": "interactive" if interactive else "async",
            "execution_id": str(execution.execution_id),
            "task_id": str(execution.execution_id),
        }

