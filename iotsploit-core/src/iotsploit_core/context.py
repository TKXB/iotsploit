"""
Plugin Context for Backend Injection.

This module provides a typed context object for injecting platform-specific
backends into plugins. This avoids magic string keys and provides better
type safety and IDE support.
"""

from dataclasses import dataclass
from typing import Optional

from iotsploit_core.ports.wifi_backend import WifiBackend


@dataclass
class PluginContext:
    """
    Context object for injecting platform-specific backends into plugins.
    
    This provides a structured way to pass backends to plugins, avoiding
    dictionary-based injection with magic string keys. As new backends are
    added, they can be added as optional fields here.
    
    Attributes:
        wifi: Optional WiFi backend instance
    """
    wifi: Optional[WifiBackend] = None
