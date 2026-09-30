"""The monitor kinds this package ships: a core source paired with a fuzzer policy.

They are registered under the ``iotsploit.monitors`` entry-point group, the
same way a third-party kind is, so nothing lists them by name.
"""

from __future__ import annotations

from iotsploit_core.core.monitoring.sources.mcu_core import McuCoreKind, McuCoreSource
from iotsploit_fuzzer.monitors import McuCoreMonitor


class McuCore(McuCoreKind):
    def policy(self, source: McuCoreSource) -> McuCoreMonitor:
        options = source.options
        return McuCoreMonitor(
            source.entry.name,
            source.end,
            source.settle_ms,
            snapshot=source.snapshot,
            recover=source.recover,
            recovery_policy=options.recovery_policy,
            max_recoveries=options.max_recoveries,
            expected_reset_prefixes=options.expected_reset_prefixes,
        )
