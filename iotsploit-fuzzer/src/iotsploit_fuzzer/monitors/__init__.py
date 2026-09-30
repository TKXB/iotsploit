"""Campaign policies, one per monitor kind. See ``monitoring.target_monitor``."""

from .health import HealthMonitor
from .mcu_core import McuCoreMonitor

__all__ = ["HealthMonitor", "McuCoreMonitor"]
