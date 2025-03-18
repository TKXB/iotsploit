import usb.core
import usb.util
import logging
import uuid
import os
from pathlib import Path
from sat_toolkit.models.Device_Model import Device, DeviceType, USBDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.tools.firmware_mgr import FirmwareManager
from plugins.devices.greatfet.protocol import get_version_number  # Updated to use absolute import

logger = logging.getLogger(__name__)

class GreatFETDriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.usb_device = None
        # Initialize firmware manager
        self.firmware_mgr = FirmwareManager.Instance()
        self.supported_commands = {
            "get_version": "Get GreatFET device version",
            "test_command": "Send test command to GreatFET device",
            "flash_firmware_sram": "Flash firmware to GreatFET device's SRAM (temporary)",
            "flash_firmware_spiflash": "Flash firmware to GreatFET device's SPI flash (permanent)"
        }
    
    def _scan_impl(self) -> list:
        usb_devices = usb.core.find(find_all=True, idVendor=0x1d50, idProduct=0x60e6)
        if usb_devices is None:
            logger.info("No GreatFET devices found.")
            return []
        found_devices = []
        for usb_dev in usb_devices:
            try:
                serial_number = usb.util.get_string(usb_dev, usb_dev.iSerialNumber)
                logger.info(f"Found GreatFET device with serial number: {serial_number}")
                # Store the raw USB device in a temporary attribute
                self.usb_device = usb_dev
                
                # Create a deterministic device ID based on the device type and serial number
                # This ensures the same physical device always gets the same ID
                device_id = f"greatfet_{serial_number}"
                
                device = USBDevice(
                    device_id=device_id,
                    name="GreatFET",
                    vendor_id=hex(0x1d50),
                    product_id=hex(0x60e6),
                    attributes={
                        'serial_number': serial_number,
                        # Don't include the raw USB device in attributes
                    }
                )
                found_devices.append(device)
            except usb.core.USBError as e:
                logger.error(f"Could not access device: {e}")
                continue
        return found_devices

    def _initialize_impl(self, device: USBDevice) -> bool:
        if device.device_type != DeviceType.USB:
            logger.error(f"Invalid device type: {device.device_type}")
            raise ValueError("This plugin only supports USB devices")
        if 'usb_device' not in device.attributes:
            scanned_devices = self._scan_impl()
            matching_device = next((d for d in scanned_devices if d.attributes.get('serial_number') == device.attributes.get('serial_number')), None)
            if not matching_device:
                raise ValueError("No compatible GreatFET device found. Unable to initialize.")
            device.attributes.update(matching_device.attributes)
        logger.info(f"Initializing GreatFET device: {device.name}")
        self.usb_device = device.attributes.get('usb_device')
        return True

    def _connect_impl(self, device: USBDevice) -> bool:
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

    def _command_impl(self, device: USBDevice, command: str, args: dict = None) -> str:
        if args is None:
            args = {}
            
        if not self.usb_device and command not in ["flash_firmware_sram", "flash_firmware_spiflash"]:
            logger.error(f"Cannot send command: GreatFET device {device.name} is not connected")
            raise RuntimeError("Device not connected")
            
        if command == "get_version":
            version = get_version_number(device)
            logger.info(f"Retrieved version for {device.name}: {version}")
            return version
        elif command == "flash_firmware_sram":
            return self._handle_flash_firmware(device, args, target="sram")
        elif command == "flash_firmware_spiflash":
            return self._handle_flash_firmware(device, args, target="spi")
        else:
            logger.info(f"Sent command '{command}' to GreatFET device {device.name}")
            return f"Command '{command}' sent"
            
    def _handle_flash_firmware(self, device: USBDevice, args: dict, target: str) -> dict:
        """
        Flash firmware to GreatFET device using FirmwareManager
        
        Args:
            device: The device to flash
            args: Command arguments
            target: Target memory ('sram' or 'spi')
        """
        try:
            # Get the firmware directory path
            current_dir = Path(__file__).parent
            firmware_dir = current_dir / "firmware"
            
            # Check if firmware file exists or use the one specified in args
            firmware_name = args.get('firmware_name', 'greatfet_usb_origin')
            firmware_path = args.get('firmware_path')
            
            if not firmware_path:
                firmware_path = firmware_dir / f"{firmware_name}.bin"
                if not firmware_path.exists():
                    error_msg = f"Firmware file not found: {firmware_path}"
                    logger.error(error_msg)
                    return {"status": "error", "message": error_msg}
            
            # Get/set greatfet_firmware tool path if provided
            tool_path = args.get('tool_path')
            
            # Determine full firmware name with target suffix
            target_suffix = "_sram" if target == "sram" else "_spiflash"
            full_firmware_name = f"{firmware_name}{target_suffix}"
            
            # Register firmware with the firmware manager if not already registered
            if not self.firmware_mgr.get_firmware_info(full_firmware_name):
                logger.info(f"Registering firmware: {full_firmware_name}")
                
                flash_options = {
                    "target": target,
                    "serial": device.attributes.get('serial_number')
                }
                
                if tool_path:
                    flash_options["tool_path"] = tool_path
                
                self.firmware_mgr.add_firmware(
                    name=full_firmware_name,
                    path=str(firmware_path),
                    device_type="greatfet",
                    version="1.0.0",
                    flash_options=flash_options
                )
            
            # Prepare flash options
            flash_options = {
                "target": target,
                "serial": device.attributes.get('serial_number')
            }
            
            if tool_path:
                flash_options["tool_path"] = tool_path
            
            # Flash the firmware
            target_desc = "SRAM (temporary)" if target == "sram" else "SPI flash (permanent)"
            logger.info(f"Flashing {firmware_name} to GreatFET device {target_desc}")
            result = self.firmware_mgr.flash_firmware(full_firmware_name, flash_options)
            
            if result:
                success_msg = f"GreatFET firmware flashed successfully to {target_desc}"
                logger.info(success_msg)
                return {"status": "success", "message": success_msg}
            else:
                error_msg = f"Failed to flash GreatFET firmware to {target_desc}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
                
        except Exception as e:
            error_msg = f"Error flashing GreatFET firmware: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    def _reset_impl(self, device: USBDevice) -> bool:
        if self.usb_device:
            try:
                self.usb_device.reset()
                logger.info(f"Reset GreatFET device: {device.name}")
                return True
            except usb.core.USBError as e:
                logger.error(f"Failed to reset GreatFET device {device.name}: {e}")
                return False
        else:
            logger.error(f"Cannot reset: GreatFET device {device.name} is not connected")
            return False

    def _close_impl(self, device: USBDevice) -> bool:
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

if __name__ == "__main__":
    from sat_toolkit.models.Device_Model import USBDevice
    driver = GreatFETDriver()
    found_devices = driver._scan_impl()
    if found_devices:
        test_device = found_devices[0]
        print(f"GreatFET Device Found: {test_device}")
        try:
            if driver._initialize_impl(test_device):
                if driver._connect_impl(test_device):
                    print("Device connected successfully.")
                    result = driver._command_impl(test_device, "test_command")
                    print(result)
                    version = driver._command_impl(test_device, "get_version")
                    print(f"GreatFET Version: {version}")
                    driver._reset_impl(test_device)
                    if driver._close_impl(test_device):
                        print("Device closed successfully.")
                    else:
                        print("Failed to close device.")
                else:
                    print("Failed to connect to device.")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("No GreatFET devices found.")