"""
Platform Distribution Module (Scapy-Style).

This module provides platform-specific backend implementations based on the
current platform. It uses conditional imports to select the appropriate
platform adapters at import time.
"""

from iotsploit_core.platforms.consts import LINUX, DARWIN, WINDOWS

if LINUX:
    from iotsploit_platforms.adapters.platforms.linux import wifi_backend
elif DARWIN:
    from iotsploit_platforms.adapters.platforms.darwin import wifi_backend
elif WINDOWS:
    from iotsploit_platforms.adapters.platforms.windows import wifi_backend
else:
    from iotsploit_platforms.adapters.platforms.null import wifi_backend

__all__ = ["wifi_backend"]
