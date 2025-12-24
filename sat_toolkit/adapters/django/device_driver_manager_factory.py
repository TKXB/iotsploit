from __future__ import annotations

from pathlib import Path

from sat_toolkit.adapters.django.driver_state_repo import DjangoDriverStateRepository
from sat_toolkit.adapters.memory.driver_state_repo import MemoryDriverStateRepository
from sat_toolkit.core.device_manager import DeviceDriverManager


def get_device_driver_manager(
    *,
    plugins_dir: str | Path | None = None,
    usb_config_file: str | Path | None = None,
    use_persistence: bool = True,
) -> DeviceDriverManager:
    """Composition root for Django runtime.

    Core `DeviceDriverManager` is framework-free; this wires persistence adapters.
    """

    repo = DjangoDriverStateRepository() if use_persistence else MemoryDriverStateRepository()
    return DeviceDriverManager(
        driver_state_repo=repo,
        plugins_dir=plugins_dir,
        usb_config_file=usb_config_file,
    )


