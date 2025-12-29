from __future__ import annotations

"""IoT fuzzer container (Django ring).

Stage-4: keep behavior stable by delegating to current implementations, while
giving the host app a single wiring location.
"""

from iotsploit_django.iot_fuzzer.service import (
    IoTFuzzerBridge,
    IoTFuzzerManager,
    IoTFuzzerService,
    IoTProtocolAdapter,
)


def get_fuzzer_manager() -> IoTFuzzerManager:
    return IoTFuzzerManager.get_instance()


def get_fuzzer_service() -> IoTFuzzerService:
    return IoTFuzzerService.get_instance()


def get_protocol_adapter() -> IoTProtocolAdapter:
    return IoTProtocolAdapter.get_instance()


def get_fuzzer_bridge() -> IoTFuzzerBridge:
    return IoTFuzzerBridge.get_instance()


