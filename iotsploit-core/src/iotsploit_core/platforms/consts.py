"""
Platform identification constants.

This module provides platform detection constants similar to Scapy's approach,
allowing the codebase to identify the current platform at import time.
"""

from sys import platform as _sys_platform

# Platform identification constants
LINUX = _sys_platform.startswith("linux")
DARWIN = _sys_platform.startswith("darwin")
WINDOWS = _sys_platform.startswith("win32")
BSD = "bsd" in _sys_platform

# Current platform string (for reference)
PLATFORM = _sys_platform

__all__ = [
    "LINUX",
    "DARWIN",
    "WINDOWS",
    "BSD",
    "PLATFORM",
]
