from __future__ import annotations

from typing import Any


class CeleryTaskRunner:
    """TaskRunner implementation backed by sat_toolkit Celery task."""

    def submit(
        self,
        plugin_name: str,
        target: dict | None,
        parameters: dict,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]:
        # Local import: keep adapter import side-effects minimal.
        from sat_toolkit.tasks import execute_plugin_task

        task = execute_plugin_task.delay(
            plugin_name,
            target=target,
            parameters=parameters,
        )
        return {"execution_type": "async", "task_id": task.id}


