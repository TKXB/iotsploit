import pluggy
from sat_toolkit.models.Device_Model import Device

hookspec = pluggy.HookspecMarker("device_mgr")

class DevicePluginSpec:
    @hookspec
    def scan(self, device: Device):
        """Scan the device"""

    @hookspec
    def initialize(self, device: Device):
        """Initialize the plugin for a specific device."""
    
    @hookspec
    def connect(self, device: Device):
        """Connect to the device."""

    @hookspec
    def execute(self, device: Device, target: str):
        """Execute an action on the target using the device."""

    @hookspec
    def command(self, device: Device, command: str):
        """Send a command to the device."""

    @hookspec
    def reset(self, device: Device):
        """Reset the device to its initial state."""

    @hookspec
    def close(self, device: Device):
        """Close the device."""
        