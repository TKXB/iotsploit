import logging
import pluggy
from sat_toolkit.core.device_manager import DeviceManager
from sat_toolkit.models.Device_Model import Device, DeviceType
from sat_toolkit.core.plugins.abilities.usb_a import USBAbility

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("exploit_mgr")

class USBPlugin:
    def __init__(self):
        self.manager = DeviceManager()
        logger.debug(f"DeviceManager initialized A: {self.manager}")
        self.manager.register_plugin(USBAbility())
        self.usb_device = None

    @hookimpl
    def initialize(self):
        print("Initializing USBPlugin with DeviceManagers")
        self.usb_device = Device("001", "USB Flash Drive", DeviceType.USB, {"capacity": "32GB"})
        self.manager.initialize_device(self.usb_device)

    @hookimpl
    def execute(self):
        print("Executing USBPlugin")
        if not self.usb_device:
            raise ValueError("USB device not initialized")
        self.manager.execute_on_target(self.usb_device, "example.com")

    def send_command(self, device: Device, command: str):
        print(f"Sending USB command '{command}' to device {device.name}")
        self.manager.send_command_to_device(self.usb_device, command)

    def reset(self, device: Device):
        print(f"Resetting USB device: {device.name}")
        self.manager.reset_device(self.usb_device)

def register_plugin(pm):
    usb_plugin = USBPlugin()
    pm.register(usb_plugin)

def main():
    # Create a device manager
    manager = DeviceManager()

    # Register the USB plugin
    manager.register_plugin(USBAbility())

    # Create a USB device
    usb_device = Device("001", "USB Flash Drive", DeviceType.USB, {"capacity": "32GB"})

    # Use the device manager to interact with the device
    manager.initialize_device(usb_device)
    manager.execute_on_target(usb_device, "example.com")
    manager.send_command_to_device(usb_device, "read_data")
    manager.reset_device(usb_device)

if __name__ == "__main__":
    main()