"""
Platform Distribution Module (Scapy-Style).

This module provides platform-specific backend implementations based on the
current platform. It uses conditional imports to select the appropriate
platform adapters at import time.
"""

from iotsploit_core.platforms.consts import LINUX, DARWIN, WINDOWS, PLATFORM
from iotsploit_core.utils.exceptions import NotSupportedError

if LINUX:
    from iotsploit_platforms.adapters.platforms.linux import wifi_backend
elif DARWIN:
    from iotsploit_platforms.adapters.platforms.darwin import wifi_backend
elif WINDOWS:
    from iotsploit_platforms.adapters.platforms.windows import wifi_backend
else:
    raise NotSupportedError(f"Platform {PLATFORM} not supported")

__all__ = ["wifi_backend"]
