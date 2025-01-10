import pluggy
import warnings
from sat_toolkit.models.Device_Model import Device
from typing import List, Optional
from enum import Enum

hookspec = pluggy.HookspecMarker("device_mgr")

"""
Scan -> Init -> Connect -> Commands -> Close
"""


class DeviceState(Enum):
    """Device lifecycle states"""
    UNKNOWN = "unknown"
    DISCOVERED = "discovered"  # After scan
    INITIALIZED = "initialized"  # After init
    CONNECTED = "connected"    # After connect
    ACTIVE = "active"         # During command execution
    DISCONNECTED = "disconnected"  # After close
    ERROR = "error"           # Error state

class DevicePluginSpec:
    """Specification for device plugin lifecycle management"""
    
    @hookspec
    def scan(self) -> List[Device]:
        """Scan for available devices.
        First step in device lifecycle.
        
        Returns:
            list[Device]: A list of discovered devices matching the configuration.
        """

    @hookspec
    def initialize(self, device: Device) -> bool:
        """Initialize the plugin for a specific device.
        Second step in device lifecycle.
        
        Args:
            device: Device to initialize
            
        Returns:
            bool: True if initialization successful
        """

    @hookspec 
    def connect(self, device: Device) -> bool:
        """Connect to the device.
        Third step in device lifecycle.
        
        Args:
            device: Device to connect to
            
        Returns:
            bool: True if connection successful
        """

    @hookspec
    def command(self, device: Device, command: str) -> Optional[str]:
        """Send a command to the device.
        Only available in CONNECTED state.
        
        Args:
            device: Target device
            command: Command string to execute
            
        Returns:
            Optional[str]: Command response if any
        """

    @hookspec
    def reset(self, device: Device) -> bool:
        """Reset the device to its initial state.
        Can be called from any state except UNKNOWN.
        
        Args:
            device: Device to reset
            
        Returns:
            bool: True if reset successful
        """

    @hookspec
    def close(self, device: Device) -> bool:
        """Close the device connection.
        Final step in device lifecycle.
        
        Args:
            device: Device to close
            
        Returns:
            bool: True if closed successfully
        """
    
    @hookspec
    def execute(self, device: Device, target: str):
        """Execute an action on the target using the device."""
        warnings.warn(
            "The 'execute' method is deprecated and will be removed in a future release. "
            "Please use the 'command' method instead.",
            DeprecationWarning,
            stacklevel=2
        )
