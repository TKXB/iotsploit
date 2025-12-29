"""Channels consumers (stage-5).

Stage-5 strategy:
- Keep behavior stable by re-exporting legacy consumer classes.
- Fix dependency direction for a couple of wiring points so new Django ring code
  is the integration surface.
"""

from __future__ import annotations

from sat_toolkit.consumers import (  # noqa: F401
    ConsoleLogsConsumer,
    DeviceStreamConsumer,
    ExploitWebsocketConsumer,
    IoTFuzzerResultsConsumer,
    IoTFuzzerTestingConsumer,
    SystemUsageConsumer,
)

# Note: we intentionally keep the consumer implementations in sat_toolkit for
# now. Later refactors can move implementations here and swap imports to use
# `iotsploit_django.composition_root.wiring`.

__all__ = [
    "SystemUsageConsumer",
    "ExploitWebsocketConsumer",
    "DeviceStreamConsumer",
    "ConsoleLogsConsumer",
    "IoTFuzzerTestingConsumer",
    "IoTFuzzerResultsConsumer",
]


