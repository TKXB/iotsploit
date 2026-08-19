"""Channels consumers (stage-5.5).

Goal: iotsploit_django runtime must not import legacy modules.
"""

from __future__ import annotations

from iotsploit_django.websocket.consumers_impl import (  # noqa: F401
    ConsoleLogsConsumer,
    DeviceStreamConsumer,
    ExploitWebsocketConsumer,
    PluginExecutionConsumer,
    IoTFuzzerResultsConsumer,
    IoTFuzzerTestingConsumer,
    SystemUsageConsumer,
)

# Note: current implementations live in `consumers_impl.py` (copied from legacy
# and rewritten to use iotsploit_django imports).

__all__ = [
    "SystemUsageConsumer",
    "ExploitWebsocketConsumer",
    "PluginExecutionConsumer",
    "DeviceStreamConsumer",
    "ConsoleLogsConsumer",
    "IoTFuzzerTestingConsumer",
    "IoTFuzzerResultsConsumer",
]


