from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


def _context_factory():
    """
    Build PluginContext with all backends.
    
    This factory is called by ExploitPluginManager before executing plugins.
    Configuration is automatically read from environment variables by
    iotsploit_platforms.selector.build_context().
    
    Returns:
        PluginContext instance with all configured backends
    """
    try:
        from iotsploit_platforms.selector import build_context
    except ImportError:
        raise ImportError(
            "iotsploit-platforms is required for plugin execution. "
            "Install with: pip install iotsploit-django[platforms]"
        )
    return build_context()


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
        context_factory=_context_factory,
        observation_sink=_build_observation_sink(),
    )


def _build_observation_sink():
    """Persistence for scan observations, or None if it cannot be reached.

    Returning None degrades to "observations are not recorded"; it must never
    stop plugins from running.
    """
    try:
        from iotsploit_django.adapters.django.observation_repository import ObservationRepository

        return ObservationRepository()
    except Exception as exc:  # pragma: no cover - defensive wiring
        logger.warning("Observation sink unavailable, scans will not be recorded: %s", exc)
        return None


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


