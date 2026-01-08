from __future__ import annotations

# Ensure Celery app is configured (broker/result backend from Django settings)
# before importing tasks defined with `@shared_task`.
from iotsploit_django.tasks.celery_app import app as _celery_app  # noqa: F401

# Stage-5.5: keep behavior stable while removing legacy runtime dependencies.
from iotsploit_django.tasks.legacy_tasks_impl import (  # noqa: F401
    generate_fuzzing_report,
    process_fuzzing_results,
    run_fuzzing_campaign,
)

__all__ = [
    "run_fuzzing_campaign",
    "process_fuzzing_results",
    "generate_fuzzing_report",
]


