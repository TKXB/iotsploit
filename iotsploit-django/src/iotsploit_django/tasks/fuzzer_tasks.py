from __future__ import annotations

# Stage-5: keep behavior stable by re-exporting legacy fuzzer Celery tasks.
from sat_toolkit.tasks import (  # noqa: F401
    generate_fuzzing_report,
    process_fuzzing_results,
    run_fuzzing_campaign,
)

__all__ = [
    "run_fuzzing_campaign",
    "process_fuzzing_results",
    "generate_fuzzing_report",
]


