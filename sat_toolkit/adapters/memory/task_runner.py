from __future__ import annotations

from typing import Any


class InProcessTaskRunner:
    """Synchronous TaskRunner implementation (useful for tests/offline).

    This runner does not spawn new processes/threads; it is intended to be used when
    core decides to schedule async execution but the environment does not have Celery.
    """

    def submit(
        self,
        plugin_name: str,
        target: dict | None,
        parameters: dict,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]:
        return {
            "execution_type": "in_process",
            "plugin_name": plugin_name,
            "target": target,
            "parameters": parameters,
            "context": context,
        }


