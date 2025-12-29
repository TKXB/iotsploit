from __future__ import annotations

"""Public wiring helpers for Django HTTP/WS/tasks.

Rule: business code (views/tasks) should import dependencies from here, not
instantiate adapters directly.
"""

from pathlib import Path
from typing import Optional

from iotsploit_core.core.device_manager import DeviceDriverManager
from iotsploit_core.core.exploit_manager import ExploitPluginManager

from iotsploit_django.composition_root import core_container, fuzzer_container


_exploit_mgr: Optional[ExploitPluginManager] = None
_device_mgr: Optional[DeviceDriverManager] = None
_stream_configured: bool = False


def get_exploit_plugin_manager(
    *,
    plugins_dir: str | Path | None = None,
    use_celery: bool = True,
) -> ExploitPluginManager:
    global _exploit_mgr
    if _exploit_mgr is None:
        _exploit_mgr = core_container.build_exploit_plugin_manager(
            plugins_dir=plugins_dir,
            use_celery=use_celery,
        )
    return _exploit_mgr


def get_device_driver_manager(
    *,
    plugins_dir: str | Path | None = None,
    usb_config_file: str | Path | None = None,
    use_persistence: bool = True,
) -> DeviceDriverManager:
    global _device_mgr
    if _device_mgr is None:
        _device_mgr = core_container.build_device_driver_manager(
            plugins_dir=plugins_dir,
            usb_config_file=usb_config_file,
            use_persistence=use_persistence,
        )
    return _device_mgr


def ensure_stream_backend_configured() -> None:
    global _stream_configured
    if not _stream_configured:
        core_container.configure_stream_backend()
        _stream_configured = True


# IoT fuzzer wiring passthroughs (stage-4).
get_fuzzer_manager = fuzzer_container.get_fuzzer_manager
get_fuzzer_service = fuzzer_container.get_fuzzer_service
get_protocol_adapter = fuzzer_container.get_protocol_adapter
get_fuzzer_bridge = fuzzer_container.get_fuzzer_bridge


