from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from iotsploit_core.core.device_manager import DeviceDriverManager
from iotsploit_core.core.exploit_manager import ExploitPluginManager

from iotsploit_mcp.adapters.http_driver_state_repo import HttpDriverStateRepository
from iotsploit_mcp.adapters.http_plugin_group_repo import HttpPluginGroupRepository
from iotsploit_mcp.adapters.http_plugin_meta_repo import HttpPluginMetaRepository
from iotsploit_mcp.adapters.task_runner_local import LocalTaskRunner

logger = logging.getLogger(__name__)


def _default_exploit_plugins_dir() -> Path:
    env = os.getenv("IOTSPLOIT_EXPLOIT_PLUGINS_DIR") or os.getenv("SAT_EXPLOIT_PLUGINS_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "plugins" / "exploits"


def build_device_manager(
    *,
    plugins_dir: str | Path | None = None,
    usb_config_file: str | Path | None = None,
    django_api_base_url: Optional[str] = None,
) -> DeviceDriverManager:
    """Build a framework-free DeviceDriverManager for MCP runtime.

    Driver states are sourced from iotsploit_django HTTP API (single source of truth).
    """

    repo = (
        HttpDriverStateRepository.from_env()
        if django_api_base_url is None
        else HttpDriverStateRepository(base_url=django_api_base_url)
    )

    # Fail fast so we don't start with wrong/unknown driver states.
    _ = repo.list_enabled()

    return DeviceDriverManager(
        driver_state_repo=repo,
        plugins_dir=plugins_dir,
        usb_config_file=usb_config_file,
    )


def build_exploit_manager(*, django_api_base_url: Optional[str] = None, plugins_dir: str | Path | None = None) -> ExploitPluginManager:
    """Build ExploitPluginManager for MCP runtime.

    SSOT mode: enabled plugins and group specs come from Django over HTTP.
    Discovery reporting (upsert) is allowed but MUST NOT override enabled/disabled decisions.
    """
    plugin_repo = (
        HttpPluginMetaRepository.from_env()
        if django_api_base_url is None
        else HttpPluginMetaRepository(base_url=django_api_base_url)
    )
    group_repo = (
        HttpPluginGroupRepository.from_env()
        if django_api_base_url is None
        else HttpPluginGroupRepository(base_url=django_api_base_url)
    )

    # Fail fast: ensure Django API reachable & returns a well-formed payload.
    _ = plugin_repo.list_enabled()
    _ = group_repo.list_enabled_groups()

    return ExploitPluginManager(
        plugin_repo=plugin_repo,
        group_repo=group_repo,
        task_runner=LocalTaskRunner(),
        plugins_dir=Path(plugins_dir) if plugins_dir is not None else _default_exploit_plugins_dir(),
    )


