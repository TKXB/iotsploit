from __future__ import annotations

from pathlib import Path
from typing import Optional

from iotsploit_core.core.device_manager import DeviceDriverManager
from iotsploit_core.core.exploit_manager import ExploitPluginManager
from iotsploit_core.core.stream_manager import StreamManager

from iotsploit_django.ports_impl.driver_state_repo import DjangoDriverStateRepository
from iotsploit_django.ports_impl.plugin_repo import DjangoPluginGroupRepository, DjangoPluginMetaRepository
from iotsploit_django.ports_impl.stream_backend import DjangoStreamBackend
from iotsploit_django.ports_impl.task_runner import CeleryTaskRunner

from iotsploit_django.adapters.memory.driver_state_repo import MemoryDriverStateRepository
from iotsploit_django.adapters.memory.task_runner import InProcessTaskRunner
from iotsploit_django.config import DEVICE_PLUGINS_DIR


def build_exploit_plugin_manager(
    *,
    plugins_dir: str | Path | None = None,
    use_celery: bool = True,
) -> ExploitPluginManager:
    """Build `iotsploit_core` exploit plugin manager with Django adapters."""

    repo = DjangoPluginMetaRepository()
    group_repo = DjangoPluginGroupRepository()
    runner = CeleryTaskRunner() if use_celery else InProcessTaskRunner()
    return ExploitPluginManager(
        plugin_repo=repo,
        group_repo=group_repo,
        task_runner=runner,
        plugins_dir=plugins_dir,
    )


def build_device_driver_manager(
    *,
    plugins_dir: str | Path | None = None,
    usb_config_file: str | Path | None = None,
    use_persistence: bool = True,
) -> DeviceDriverManager:
    """Build `iotsploit_core` device driver manager with Django adapters."""

    repo = DjangoDriverStateRepository() if use_persistence else MemoryDriverStateRepository()

    if plugins_dir is None:
        plugins_dir = DEVICE_PLUGINS_DIR
    if usb_config_file is None:
        # repo_root/conf/usb_devices.json
        usb_config_file = str(Path(__file__).resolve().parents[4] / "conf" / "usb_devices.json")

    return DeviceDriverManager(
        driver_state_repo=repo,
        plugins_dir=plugins_dir,
        usb_config_file=usb_config_file,
    )


def configure_stream_backend(backend: Optional[DjangoStreamBackend] = None) -> None:
    """Configure core `StreamManager` backend once for the Django runtime."""

    StreamManager.configure_backend(backend or DjangoStreamBackend())


