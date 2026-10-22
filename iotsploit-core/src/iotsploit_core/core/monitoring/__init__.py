"""Target monitoring: sources that turn hardware into observations.

Sources sample; they never decide whether a reading fails a test case. That is
the campaign policy's job (``iotsploit_fuzzer.monitors``). See
``docs/exec-plans/active/target_monitor_architecture_plan.md``.
"""

from iotsploit_core.core.monitoring.catalog import TargetCatalog
from iotsploit_core.core.monitoring.kind import MonitorContext, MonitorKind, load_monitor_kinds
from iotsploit_core.core.monitoring.service import MonitorService, MonitorSession
from iotsploit_core.core.monitoring.source import MonitorPlanEntry, MonitorSource, SourceRegistry, parse_plan

__all__ = [
    "MonitorContext",
    "MonitorKind",
    "MonitorPlanEntry",
    "MonitorService",
    "MonitorSession",
    "MonitorSource",
    "SourceRegistry",
    "TargetCatalog",
    "load_monitor_kinds",
    "parse_plan",
]
