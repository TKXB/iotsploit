"""
WiFi Backend Interface (Port).

This module defines the stable interface for WiFi operations across different platforms.
Platform-specific implementations should be provided in adapter modules.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple

from iotsploit_core.utils.exceptions import NotSupportedError


class WifiBackend(ABC):
    """
    Abstract base class for WiFi backend implementations.
    
    This interface provides a unified API for WiFi operations regardless of platform.
    Platform-specific implementations should inherit from this class and implement
    all abstract methods.
    """

    @abstractmethod
    def scan(self) -> List[Dict[str, Any]]:
        """
        Scan for available WiFi networks.
        
        Returns:
            List of dictionaries containing WiFi network information.
            Each dictionary should contain at least:
            - ssid: str - Network SSID
            - bssid: str - Network BSSID (MAC address)
            - signal: int - Signal strength (optional)
            - security: str - Security type (optional)
        
        Raises:
            NotSupportedError: If scanning is not supported on this platform
        """
        pass

    @abstractmethod
    def sta_connect(self, ssid: str, passwd: str) -> None:
        """
        Connect to a WiFi network in station (STA) mode.
        
        Args:
            ssid: Network SSID to connect to
            passwd: Network password (empty string for open networks)
        
        Raises:
            NotSupportedError: If STA mode is not supported on this platform
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    def sta_disconnect(self) -> None:
        """
        Disconnect from the current WiFi network in station mode.
        
        Raises:
            NotSupportedError: If STA mode is not supported on this platform
        """
        pass

    @abstractmethod
    def ap_start(self, ssid: Optional[str] = None, passwd: Optional[str] = None, wpa_mode: int = 2) -> Tuple[str, str]:
        """
        Start WiFi access point (AP) mode.
        
        Args:
            ssid: AP SSID (if None, a default will be generated)
            passwd: AP password (if None, a default will be used)
            wpa_mode: WPA mode (1=WPA only, 2=WPA2 only, 3=both)
        
        Returns:
            Tuple of (ssid, passwd) that were actually used
        
        Raises:
            NotSupportedError: If AP mode is not supported on this platform
        """
        pass

    @abstractmethod
    def ap_stop(self) -> None:
        """
        Stop WiFi access point (AP) mode.
        
        Raises:
            NotSupportedError: If AP mode is not supported on this platform
        """
        pass

    def status(self) -> Dict[str, Any]:
        """
        Get current WiFi status.
        
        Returns:
            Dictionary containing current WiFi status information.
            Should include at least:
            - wifi_mode: str - Current mode ("STA", "AP", or "IDLE")
            - sta_status: dict - Station mode status (if in STA mode)
            - ap_status: dict - AP mode status (if in AP mode)
        
        Note:
            This method has a default implementation that returns basic info.
            Subclasses can override for platform-specific details.
        """
        return {
            "wifi_mode": "IDLE",
        }

    def query_wifi_info_by_bssid(self, bssid: str) -> Optional[List[Dict[str, Any]]]:
        """
        Query WiFi network information by BSSID.
        
        Args:
            bssid: BSSID (MAC address) to search for
        
        Returns:
            List of matching WiFi networks, or None if scan failed
        
        Note:
            Default implementation performs a scan and filters by BSSID.
            Subclasses can override for more efficient platform-specific implementations.
        """
        networks = self.scan()
        bssid_lower = bssid.lower()
        return [net for net in networks if net.get("bssid", "").lower() == bssid_lower]

    def query_wifi_info_by_ssid(self, ssid: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Query WiFi network information by SSID.
        
        Args:
            ssid: SSID to search for (if None, returns all networks)
        
        Returns:
            List of matching WiFi networks, or None if scan failed
        
        Note:
            Default implementation performs a scan and filters by SSID.
            Subclasses can override for more efficient platform-specific implementations.
        """
        networks = self.scan()
        if ssid is None:
            return networks
        return [net for net in networks if net.get("ssid") == ssid]
