"""
Platform Backend Selector.

This module provides functions to select and instantiate platform-specific
backends based on the current operating system. It serves as the main entry
point for applications (CLI/Django/MCP) to obtain backend instances.

The selector automatically chooses the appropriate implementation for the
current platform and handles backend instantiation with proper parameters.

Configuration is read from environment variables:
- WiFi: IOTSPLOIT_WIFI_IFACE, IOTSPLOIT_WIFI_FORWARD_ETH
- (Add more backends here as they are implemented)
"""

import inspect
import os
from typing import Optional

from iotsploit_core.context import PluginContext
from iotsploit_core.platforms.consts import LINUX
from iotsploit_platforms.platforms import wifi_backend


# =============================================================================
# Backend Configuration from Environment
# =============================================================================

def _get_wifi_config() -> dict:
    """Get WiFi backend configuration from environment variables."""
    return {
        "wifi_iface_name": os.getenv("IOTSPLOIT_WIFI_IFACE", "wlp6s0"),
        "forward_eth_name": os.getenv("IOTSPLOIT_WIFI_FORWARD_ETH"),
    }


# TODO: Add more backend config functions as they are implemented
# def _get_bluetooth_config() -> dict:
#     return {
#         "adapter": os.getenv("IOTSPLOIT_BLUETOOTH_ADAPTER", "hci0"),
#     }


# =============================================================================
# Backend Factory Functions
# =============================================================================

def get_wifi_backend(
    wifi_iface_name: Optional[str] = None,
    forward_eth_name: Optional[str] = None
) -> wifi_backend:
    """
    Get a WiFi backend instance for the current platform.
    
    This function automatically selects the appropriate WiFi backend
    implementation based on the current operating system (Linux/Windows/macOS)
    and returns an instantiated backend.
    
    Args:
        wifi_iface_name: WiFi interface name. If None, reads from IOTSPLOIT_WIFI_IFACE env var.
        forward_eth_name: Ethernet interface for forwarding. If None, reads from IOTSPLOIT_WIFI_FORWARD_ETH.
    
    Returns:
        An instance of the platform-specific WiFi backend class
        
    Example:
        >>> backend = get_wifi_backend()  # Uses env vars
        >>> backend = get_wifi_backend(wifi_iface_name="wlan0")  # Override
    """
    # Get config from env if not provided
    if wifi_iface_name is None or forward_eth_name is None:
        env_config = _get_wifi_config()
        if wifi_iface_name is None:
            wifi_iface_name = env_config["wifi_iface_name"]
        if forward_eth_name is None:
            forward_eth_name = env_config["forward_eth_name"]
    
    # wifi_backend is the class imported from platforms/__init__.py
    # which is already platform-specific (LinuxWifiBackend, WindowsWifiBackend, etc.)
    
    # Check if the constructor accepts forward_eth_name parameter
    # Linux backend accepts it, Windows/Darwin don't
    sig = inspect.signature(wifi_backend.__init__)
    params = sig.parameters
    
    if 'forward_eth_name' in params:
        # Linux backend - supports forward_eth_name
        return wifi_backend(
            wifi_iface_name=wifi_iface_name,
            forward_eth_name=forward_eth_name
        )
    else:
        # Windows/Darwin backend - only accepts wifi_iface_name
        return wifi_backend(wifi_iface_name=wifi_iface_name)


# =============================================================================
# Context Builder (Main Entry Point)
# =============================================================================

def build_context() -> PluginContext:
    """
    Build a PluginContext with all available backends.
    
    This function creates a structured context object containing all
    platform-specific backends. Configuration is automatically read from
    environment variables.
    
    This is the recommended way to inject backends into plugins.
    Adding a new backend only requires:
    1. Add field to PluginContext
    2. Add _get_xxx_config() function
    3. Add get_xxx_backend() function
    4. Add backend instance to PluginContext here
    
    Environment variables:
    - WiFi: IOTSPLOIT_WIFI_IFACE, IOTSPLOIT_WIFI_FORWARD_ETH
    - (More backends as implemented)
    
    Returns:
        A PluginContext instance with all backends initialized
        
    Example:
        >>> ctx = build_context()  # Reads config from env
        >>> plugin.initialize(ctx)
        >>> # Plugin can access ctx.wifi, ctx.bluetooth, etc.
    """
    return PluginContext(
        wifi=get_wifi_backend(),  # Uses env vars automatically
        # bluetooth=get_bluetooth_backend(),  # TODO: Add when implemented
        # camera=get_camera_backend(),        # TODO: Add when implemented
    )
