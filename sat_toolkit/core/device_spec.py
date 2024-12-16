import pluggy
import warnings
from sat_toolkit.models.Device_Model import Device
from typing import List
hookspec = pluggy.HookspecMarker("device_mgr")

"""
Scan -> Init -> Connect -> Commands -> Close
"""

class DevicePluginSpec:
    @hookspec
    def scan(self) -> List[Device]:
        """Scan for available devices.
            
        Returns:
            list[Device]: A list of discovered devices matching the configuration.
        """

    @hookspec
    def initialize(self, device: Device):
        """Initialize the plugin for a specific device."""
    
    @hookspec
    def connect(self, device: Device):
        """Connect to the device."""

    @hookspec
    def command(self, device: Device, command: str):
        """Send a command to the device."""

    @hookspec
    def execute(self, device: Device, target: str):
        """Execute an action on the target using the device."""
        warnings.warn(
            "The 'execute' method is deprecated and will be removed in a future release. "
            "Please use the 'command' method instead.",
            DeprecationWarning,
            stacklevel=2
        )

    @hookspec
    def reset(self, device: Device):
        """Reset the device to its initial state."""

    @hookspec
    def close(self, device: Device):
        """Close the device."""
        