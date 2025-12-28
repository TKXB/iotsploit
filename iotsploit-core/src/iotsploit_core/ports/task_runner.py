from __future__ import annotations

from typing import Any, Protocol


class TaskRunner(Protocol):
    """Abstraction for async/background execution (e.g. Celery).

    NOTE: We intentionally submit "business parameters" rather than a callable to avoid
    Celery serialization / closure issues.
    """

    def submit(
        self,
        plugin_name: str,
        target: dict | None,
        parameters: dict,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]: ...


