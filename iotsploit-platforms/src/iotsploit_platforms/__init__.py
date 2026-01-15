"""
IoTSploit Platform Adapters Package.

This package provides platform-specific implementations for WiFi, Input, and SSH backends.
"""

from iotsploit_platforms.selector import build_context, get_wifi_backend

__version__ = "0.1.0"
__all__ = ["get_wifi_backend", "build_context"]
