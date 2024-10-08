import usb.core
import usb.util
import pluggy
import logging
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, USBDevice
import uuid
from .protocol import get_version_number  # Import the get_version_number function

logger = logging.getLogger(__name__)

hookimpl = pluggy.HookimplMarker("device_mgr")

# Define the vendor and product IDs for GreatFET devices
GREATFET_VENDOR_ID = 0x1d50
GREATFET_PRODUCT_ID = 0x60e6

class GreatFETDriver:
    def __init__(self):
        self.usb_device = None

    @hookimpl
    def scan(self):
        devices = usb.core.find(find_all=True, idVendor=GREATFET_VENDOR_ID, idProduct=GREATFET_PRODUCT_ID)
        
        if devices is None:
            logger.info("No GreatFET devices found.")
            return []

        found_devices = []
        for usb_dev in devices:
            try:
                serial_number = usb.util.get_string(usb_dev, usb_dev.iSerialNumber)
                logger.info(f"Found GreatFET device with serial number: {serial_number}")
                
                device = USBDevice(
                    device_id=str(uuid.uuid4()),
                    name="GreatFET",
                    vendor_id=hex(GREATFET_VENDOR_ID),
                    product_id=hex(GREATFET_PRODUCT_ID),
                    attributes={
                        'serial_number': serial_number,
                        'usb_device': usb_dev,
                    }
                )
                found_devices.append(device)
            except usb.core.USBError as e:
                logger.error(f"Could not access device: {e}")
                continue

        return found_devices

    @hookimpl
    def initialize(self, device: USBDevice):
        if device.device_type != DeviceType.USB:
            logger.error(f"Current device type: {device.device_type}")
            raise ValueError("This plugin only supports USB devices")
        
        if 'usb_device' not in device.attributes:
            found_devices = self.scan()
            matching_device = next((d for d in found_devices if d.attributes['serial_number'] == device.attributes.get('serial_number')), None)
            if not matching_device:
                raise ValueError("No compatible GreatFET device found. Unable to initialize.")
            device.attributes.update(matching_device.attributes)
        
        logger.info(f"Initializing GreatFET device: {device.name}")
        self.usb_device = device.attributes['usb_device']

    @hookimpl
    def connect(self, device: USBDevice):
        if not self.usb_device:
            logger.error("USB device object not found. Please initialize first.")
            return False

        try:
            if self.usb_device.is_kernel_driver_active(0):
                self.usb_device.detach_kernel_driver(0)
            
            self.usb_device.set_configuration()
            logger.info(f"GreatFET device {device.name} connected successfully.")
            return True
        except usb.core.USBError as e:
            logger.error(f"Failed to connect to GreatFET device {device.name}: {e}")
            return False

    @hookimpl
    def execute(self, device: USBDevice, target: str):
        logger.info(f"Executing action on {target} using GreatFET device {device.name}")
        # Implement specific GreatFET execution logic here

    @hookimpl
    def send_command(self, device: USBDevice, command: str):
        if self.usb_device:
            # Implement GreatFET-specific command sending logic here
            logger.info(f"Sent command '{command}' to GreatFET device {device.name}")
        else:
            logger.error(f"Cannot send command: GreatFET device {device.name} is not connected")

    @hookimpl
    def reset(self, device: USBDevice):
        if self.usb_device:
            self.usb_device.reset()
            logger.info(f"Reset GreatFET device: {device.name}")
        else:
            logger.error(f"Cannot reset: GreatFET device {device.name} is not connected")

    @hookimpl
    def close(self, device: USBDevice):
        if not self.usb_device:
            logger.error("USB device object not found. Nothing to close.")
            return False

        try:
            for configuration in self.usb_device:
                for interface in configuration:
                    if self.usb_device.is_kernel_driver_active(interface.bInterfaceNumber):
                        self.usb_device.detach_kernel_driver(interface.bInterfaceNumber)
                    usb.util.release_interface(self.usb_device, interface.bInterfaceNumber)

            self.usb_device.reset()
            self.usb_device = None
            logger.info(f"GreatFET device {device.name} closed successfully.")
            return True
        except usb.core.USBError as e:
            logger.error(f"Failed to close GreatFET device {device.name}: {e}")
            return False

def register_plugin(pm):
    greatfet_ability = GreatFETDriver()
    pm.register(greatfet_ability)

# Example usage
if __name__ == "__main__":
    from sat_toolkit.models.Device_Model import USBDevice
    
    ability = GreatFETDriver()
    
    found_devices = ability.scan()
    if found_devices:
        test_device = found_devices[0]  # Use the first found device
        print(f"GreatFET Device Found: {test_device}")
        ability.initialize(test_device)
        if ability.connect(test_device):
            print("Device connected successfully.")
            # Perform some operations here
            ability.send_command(test_device, "test_command")
            
            # Get and print the version number
            version = get_version_number(test_device)
            print(f"GreatFET Version: {version}")
            
            ability.reset(test_device)
            if ability.close(test_device):
                print("Device closed successfully.")
            else:
                print("Failed to close device.")
        else:
            print("Failed to connect to device.")
    else:
        print("No GreatFET devices found.")