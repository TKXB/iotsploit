"""Fallback adapters for unsupported operating systems."""

from iotsploit_platforms.adapters.platforms.null.wifi_backend import wifi_backend

__all__ = ["wifi_backend"]
