from __future__ import annotations

from sat_toolkit.adapters.django.device_driver_manager_factory import get_device_driver_manager
from iotsploit_core.core.device_registry import DeviceRegistry


def get_device_registry(*, use_persistence: bool = True) -> DeviceRegistry:
    """Composition root for Django runtime."""

    driver_manager = get_device_driver_manager(use_persistence=use_persistence)
    return DeviceRegistry.get_instance(driver_manager=driver_manager)


