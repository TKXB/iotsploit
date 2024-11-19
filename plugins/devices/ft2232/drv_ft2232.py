import usb.core
import usb.util
import pluggy
import logging
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, USBDevice
import uuid
from plugins.devices.ft2232.protocol import (
    create_ft2232_interface, close_ft2232_interface,
    uart_read, uart_write, spi_exchange, jtag_write_tms, jtag_write_tdi
)

logger = logging.getLogger(__name__)

hookimpl = pluggy.HookimplMarker("device_mgr")

# Define the vendor and product IDs for FT2232 devices
FT2232_VENDOR_ID = 0x0403
FT2232_PRODUCT_ID = 0x6010

class FT2232Driver:
    def __init__(self):
        self.ft2232_interface = None
        self.mode = None

    @hookimpl
    def scan(self):
        devices = usb.core.find(find_all=True, idVendor=FT2232_VENDOR_ID, idProduct=FT2232_PRODUCT_ID)
        
        if devices is None:
            logger.info("No FT2232 devices found.")
            return []

        found_devices = []
        for usb_dev in devices:
            try:
                serial_number = usb.util.get_string(usb_dev, usb_dev.iSerialNumber)
                logger.info(f"Found FT2232 device with serial number: {serial_number}")
                
                device = USBDevice(
                    device_id=str(uuid.uuid4()),
                    name="FT2232",
                    vendor_id=hex(FT2232_VENDOR_ID),
                    product_id=hex(FT2232_PRODUCT_ID),
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
                raise ValueError("No compatible FT2232 device found. Unable to initialize.")
            device.attributes.update(matching_device.attributes)
        
        logger.info(f"Initializing FT2232 device: {device.name}")
        self.mode = device.attributes.get('mode', 'uart')  # Default to UART if not specified
        device_url = f'ftdi://ftdi:2232h/{device.attributes["serial_number"]}'
        self.ft2232_interface = create_ft2232_interface(self.mode, device_url)

    @hookimpl
    def connect(self, device: USBDevice):
        if not self.ft2232_interface:
            logger.error("FT2232 interface not initialized. Please initialize first.")
            return False

        logger.info(f"FT2232 device {device.name} connected successfully in {self.mode} mode.")
        return True

    @hookimpl
    def execute(self, device: USBDevice, target: str):
        logger.info(f"Executing action on {target} using FT2232 device {device.name}")
        # Implement specific FT2232 execution logic here based on the mode

    @hookimpl
    def send_command(self, device: USBDevice, command: str):
        if self.ft2232_interface:
            try:
                if self.mode == 'uart':
                    uart_write(self.ft2232_interface, command.encode())
                elif self.mode == 'spi':
                    spi_exchange(self.ft2232_interface, command.encode())
                elif self.mode == 'jtag':
                    jtag_write_tdi(self.ft2232_interface, command.encode())
                logger.info(f"Sent command '{command}' to FT2232 device {device.name} in {self.mode} mode")
            except Exception as e:
                logger.error(f"Failed to send command to FT2232 device {device.name}: {str(e)}")
        else:
            logger.error(f"Cannot send command: FT2232 device {device.name} is not connected")

    @hookimpl
    def reset(self, device: USBDevice):
        if self.ft2232_interface:
            close_ft2232_interface(self.mode, self.ft2232_interface)
            device_url = f'ftdi://ftdi:2232h/{device.attributes["serial_number"]}'
            self.ft2232_interface = create_ft2232_interface(self.mode, device_url)
            logger.info(f"Reset FT2232 device: {device.name}")
        else:
            logger.error(f"Cannot reset: FT2232 device {device.name} is not connected")

    @hookimpl
    def close(self, device: USBDevice):
        if not self.ft2232_interface:
            logger.error("FT2232 interface not found. Nothing to close.")
            return False

        try:
            close_ft2232_interface(self.mode, self.ft2232_interface)
            self.ft2232_interface = None
            logger.info(f"FT2232 device {device.name} closed successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to close FT2232 device {device.name}: {e}")
            return False

def register_plugin(pm):
    ft2232_ability = FT2232Driver()
    pm.register(ft2232_ability)

# Example usage
if __name__ == "__main__":
    from sat_toolkit.models.Device_Model import USBDevice
    
    ability = FT2232Driver()
    
    found_devices = ability.scan()
    if found_devices:
        test_device = found_devices[0]  # Use the first found device
        test_device.attributes['mode'] = 'uart'  # Set the mode
        print(f"FT2232 Device Found: {test_device}")
        ability.initialize(test_device)
        if ability.connect(test_device):
            print("Device connected successfully.")
            ability.send_command(test_device, "test_command")
            ability.reset(test_device)
            if ability.close(test_device):
                print("Device closed successfully.")
            else:
                print("Failed to close device.")
        else:
            print("Failed to connect to device.")
    else:
        print("No FT2232 devices found.")
