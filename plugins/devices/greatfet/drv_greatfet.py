import usb.core
import usb.util
import logging
import uuid
import os
from pathlib import Path
from sat_toolkit.domain.device import Device, DeviceType, USBDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.core.tool_service import get_firmware_service
from plugins.devices.greatfet.protocol import get_version_number  # Updated to use absolute import

logger = logging.getLogger(__name__)

class GreatFETDriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.usb_device = None
        # Initialize firmware service
        self.firmware_service = get_firmware_service()
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
        Flash firmware to GreatFET device using FirmwareService
        
        Args:
            device: The device to flash
            args: Command arguments
            target: Target memory ('sram' or 'spi')
        """
        try:
            # Get firmware name from args or use default based on target
            firmware_name = args.get('firmware_name')
            if not firmware_name:
                # Use appropriate default firmware name based on target
                firmware_name = f"greatfet_usb_origin_{target}"
            
            # Try to get firmware from the centralized manifest
            firmware_info = self.firmware_service.get_firmware_info(firmware_name)
            
            if not firmware_info:
                # If not found in manifest, check if a custom firmware_path was provided
                firmware_path = args.get('firmware_path')
                if not firmware_path:
                    error_msg = f"Firmware '{firmware_name}' not found in manifest and no firmware_path provided"
                    logger.error(error_msg)
                    return {"status": "error", "message": error_msg}
                
                # Use the provided path directly
                firmware_path_str = str(firmware_path)
            else:
                # Use firmware from manifest
                firmware_path_str = firmware_info['path']
                logger.info(f"Using firmware from manifest: {firmware_name}")
            
            # Verify firmware file exists
            if not Path(firmware_path_str).exists():
                error_msg = f"Firmware file not found: {firmware_path_str}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            # Flash the firmware using the firmware service
            target_desc = "SRAM (temporary)" if target == "sram" else "SPI flash (permanent)"
            logger.info(f"Flashing {firmware_name} to GreatFET device {target_desc}")
            
            result = self.firmware_service.greatfet.flash_firmware(
                firmware_path=firmware_path_str,
                target=target,
                serial=device.attributes.get('serial_number'),
                board=args.get('board')
            )
            
            if result.success:
                success_msg = f"GreatFET firmware flashed successfully to {target_desc} in {result.execution_time:.2f}s"
                logger.info(success_msg)
                return {
                    "status": "success", 
                    "message": success_msg,
                    "execution_time": result.execution_time
                }
            else:
                error_msg = f"Failed to flash GreatFET firmware to {target_desc}: {result.stderr or 'Unknown error'}"
                logger.error(error_msg)
                return {
                    "status": "error", 
                    "message": error_msg,
                    "return_code": result.return_code,
                    "stderr": result.stderr
                }
                
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

    def _recovery_impl(self, device: USBDevice, recovery_type: str, **kwargs) -> dict:
        """
        Implementation of GreatFET recovery operations
        
        Supported recovery types:
        - flash_firmware_sram: Flash firmware to SRAM (temporary)
        - flash_firmware_spiflash: Flash firmware to SPI flash (permanent)
        - openocd_attach: Attach OpenOCD for debugging (future implementation)
        """
        import time
        start_time = time.time()
        
        try:
            if recovery_type == "flash_firmware_sram":
                result = self._handle_flash_firmware(device, kwargs, target="sram")
                
            elif recovery_type == "flash_firmware_spiflash":
                result = self._handle_flash_firmware(device, kwargs, target="spi")
                
            elif recovery_type == "openocd_attach":
                # OpenOCD attach functionality for GreatFET debugging
                try:
                    # Use centralized tool manager for OpenOCD availability check
                    from sat_toolkit.core.centralized_tool_manager import get_centralized_tool_manager
                    from pathlib import Path
                    centralized_manager = get_centralized_tool_manager()
                    
                    if not centralized_manager.is_tool_available('openocd'):
                        return {
                            "status": "error",
                            "message": "OpenOCD tool is not available. Please install OpenOCD first.",
                            "execution_time": time.time() - start_time
                        }
                    
                    # Get OpenOCD tool info to determine script directory
                    tool_info = centralized_manager.tool_manager.registry.get_tool('openocd')
                    if not tool_info or not tool_info.path:
                        return {
                            "status": "error",
                            "message": "OpenOCD tool path not found.",
                            "execution_time": time.time() - start_time
                        }
                    
                    # Dynamic path resolution for OpenOCD tcl directory
                    openocd_path = Path(tool_info.path)
                    tcl_dir = openocd_path.parent.parent / "tcl"  # For /path/to/openocd/src/openocd -> /path/to/openocd/tcl
                    
                    # Build OpenOCD command arguments for GreatFET using NuttX configuration
                    if tcl_dir.exists():
                        # Use -s parameter to specify script search directory
                        openocd_args = [
                            '-s', str(tcl_dir),
                            '-f', 'flash_nuttx.cfg'
                        ]
                    else:
                        # Fallback to system default paths
                        openocd_args = [
                            '-f', 'flash_nuttx.cfg'
                        ]
                    
                    logger.info(f"Starting OpenOCD for GreatFET debugging with tcl dir: {tcl_dir if tcl_dir.exists() else 'system default'}")
                    
                    # Execute OpenOCD using centralized tool manager
                    result = centralized_manager.execute_tool(
                        'openocd', 
                        openocd_args,
                        timeout=10  # Short timeout to check if it starts
                    )
                    
                    # Check if OpenOCD started successfully
                    if result.success or "Listening on port" in result.stdout:
                        success_msg = "OpenOCD started successfully for GreatFET debugging"
                        logger.info(success_msg)
                        return {
                            "status": "success",
                            "message": success_msg,
                            "execution_time": time.time() - start_time
                        }
                    else:
                        error_msg = f"Failed to start OpenOCD: {result.stderr or 'Unknown error'}"
                        logger.error(error_msg)
                        return {
                            "status": "error",
                            "message": error_msg,
                            "execution_time": time.time() - start_time
                        }
                        
                except Exception as e:
                    error_msg = f"Error starting OpenOCD for GreatFET: {str(e)}"
                    logger.error(error_msg)
                    return {
                        "status": "error",
                        "message": error_msg,
                        "execution_time": time.time() - start_time
                    }
                
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported recovery operation: {recovery_type}",
                    "execution_time": time.time() - start_time
                }
            
            # Add execution time to result
            if isinstance(result, dict):
                result["execution_time"] = time.time() - start_time
                
            return result
            
        except Exception as e:
            logger.error(f"GreatFET recovery operation '{recovery_type}' failed: {str(e)}")
            return {
                "status": "error",
                "message": f"Recovery operation failed: {str(e)}",
                "execution_time": time.time() - start_time
            }

    def _get_supported_recovery_operations_impl(self) -> list:
        """
        Get list of supported recovery operations for GreatFET
        """
        return [
            "flash_firmware_sram",
            "flash_firmware_spiflash",
            "openocd_attach"  # Future implementation
        ]

if __name__ == "__main__":
    from sat_toolkit.domain.device import USBDevice
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