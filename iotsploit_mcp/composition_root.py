from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from iotsploit_core.core.device_manager import DeviceDriverManager

from iotsploit_mcp.adapters.http_driver_state_repo import HttpDriverStateRepository

logger = logging.getLogger(__name__)


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


