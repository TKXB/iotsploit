from __future__ import annotations

from pathlib import Path

from sat_toolkit.adapters.django.driver_state_repo import DjangoDriverStateRepository
from sat_toolkit.adapters.memory.driver_state_repo import MemoryDriverStateRepository
from iotsploit_core.core.device_manager import DeviceDriverManager
from sat_toolkit.config import DEVICE_PLUGINS_DIR


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
    # Ensure stable defaults regardless of CWD (Django/gunicorn may change working directory).
    if plugins_dir is None:
        plugins_dir = DEVICE_PLUGINS_DIR
    if usb_config_file is None:
        # repo_root/conf/usb_devices.json
        usb_config_file = str(Path(__file__).resolve().parents[3] / "conf" / "usb_devices.json")
    return DeviceDriverManager(
        driver_state_repo=repo,
        plugins_dir=plugins_dir,
        usb_config_file=usb_config_file,
    )


