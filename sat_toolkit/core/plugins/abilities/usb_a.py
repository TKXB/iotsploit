import pluggy
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType

hookimpl = pluggy.HookimplMarker("device_mgr")

class USBAbility:
    @hookimpl
    def initialize(self, device: Device):
        if device.device_type != DeviceType.USB:
            raise ValueError("This plugin only supports USB devices")
        print(f"Initializing USB device: {device.name}")

    @hookimpl
    def execute(self, device: Device, target: str):
        print(f"Executing USB exploit on {target} using device {device.name}")

    @hookimpl
    def send_command(self, device: Device, command: str):
        print(f"Sending USB command '{command}' to device {device.name}")

    @hookimpl
    def reset(self, device: Device):
        print(f"Resetting USB device: {device.name}")