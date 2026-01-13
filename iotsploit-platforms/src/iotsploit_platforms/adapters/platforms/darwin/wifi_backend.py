"""
Darwin (macOS) WiFi Backend Implementation.

This module provides macOS-specific WiFi backend implementation.
Currently a placeholder implementation.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple

from iotsploit_core.ports.wifi_backend import WifiBackend
from iotsploit_core.utils.exceptions import NotSupportedError

logger = logging.getLogger(__name__)


class DarwinWifiBackend(WifiBackend):
    """
    Darwin (macOS) WiFi backend implementation.
    
    This is a placeholder implementation. Full implementation would use
    macOS-specific APIs (e.g., airport, CoreWLAN framework).
    """

    def __init__(self, wifi_iface_name: Optional[str] = None):
        """
        Initialize Darwin WiFi backend.
        
        Args:
            wifi_iface_name: WiFi interface name (optional on macOS)
        """
        self.wifi_iface_name = wifi_iface_name
        self._wifi_mode = "IDLE"

    def scan(self) -> List[Dict[str, Any]]:
        """
        Scan for available WiFi networks.
        
        Raises:
            NotSupportedError: macOS WiFi scanning not yet implemented
        """
        raise NotSupportedError("WiFi scanning is not yet implemented on macOS")

    def sta_connect(self, ssid: str, passwd: str) -> None:
        """
        Connect to a WiFi network in station (STA) mode.
        
        Raises:
            NotSupportedError: macOS WiFi connection not yet implemented
        """
        raise NotSupportedError("WiFi station mode connection is not yet implemented on macOS")

    def sta_disconnect(self) -> None:
        """
        Disconnect from the current WiFi network in station mode.
        
        Raises:
            NotSupportedError: macOS WiFi disconnection not yet implemented
        """
        raise NotSupportedError("WiFi station mode disconnection is not yet implemented on macOS")

    def ap_start(self, ssid: Optional[str] = None, passwd: Optional[str] = None, wpa_mode: int = 2) -> Tuple[str, str]:
        """
        Start WiFi access point (AP) mode.
        
        Raises:
            NotSupportedError: macOS does not support WiFi AP mode
        """
        raise NotSupportedError("WiFi access point mode is not supported on macOS")

    def ap_stop(self) -> None:
        """
        Stop WiFi access point (AP) mode.
        
        Raises:
            NotSupportedError: macOS does not support WiFi AP mode
        """
        raise NotSupportedError("WiFi access point mode is not supported on macOS")

    def status(self) -> Dict[str, Any]:
        """
        Get current WiFi status.
        
        Returns:
            Dictionary containing current WiFi status information.
        """
        return {
            "wifi_mode": self._wifi_mode,
        }


# Export the backend class
wifi_backend = DarwinWifiBackend
