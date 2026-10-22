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


def open_usbtmc(config: dict, owner: str):
    """Compose one real USBTMC session with the application's shared lease."""
    from iotsploit_fuzzer.harnesses.usbtmc_harness import USBTMCHarness
    from iotsploit_fuzzer.interfaces.usbtmc_interface import USBTMCInterface
    from iotsploit_django.composition_root.wiring import get_resource_lease

    USBTMCHarness.validate(config)
    interface = USBTMCInterface(config.get("device"), lease=get_resource_lease(), owner=owner)
    try:
        harness = USBTMCHarness(interface, config)
        harness.preflight()
    except BaseException:
        interface.close()
        raise
    return interface, harness

