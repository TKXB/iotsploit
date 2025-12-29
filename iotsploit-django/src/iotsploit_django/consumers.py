"""Backward-compatible consumer exports for Django views.

Some legacy modules import from `iotsploit_django.consumers`. The canonical
implementations live under `iotsploit_django.websocket.*`.
"""

from __future__ import annotations

from iotsploit_django.websocket.consumers_impl import (  # noqa: F401
    ConsoleLogsConsumer,
    DeviceStreamConsumer,
    ExploitWebsocketConsumer,
    IoTFuzzerResultsConsumer,
    IoTFuzzerTestingConsumer,
    SystemUsageConsumer,
    console_log_buffer,
    log_buffer_lock,
)

__all__ = [
    "SystemUsageConsumer",
    "ExploitWebsocketConsumer",
    "DeviceStreamConsumer",
    "ConsoleLogsConsumer",
    "IoTFuzzerTestingConsumer",
    "IoTFuzzerResultsConsumer",
    "console_log_buffer",
    "log_buffer_lock",
]


