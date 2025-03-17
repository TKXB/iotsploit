#!/usr/bin/env python
import logging
import time
import os
import shutil
from typing import Optional, Dict, List, Any
from pathlib import Path
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, SerialDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.tools.firmware_mgr import FirmwareManager

logger = logging.getLogger(__name__)

class ECP5FPGADriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        # Define supported commands
        self.supported_commands = {
            "flash_firmware": "Flash firmware/bitstream to the ECP5 FPGA",
            "load_bitstream": "Load bitstream to FPGA SRAM (temporary)",
            "flash_bitstream": "Flash bitstream to FPGA configuration flash (permanent)",
            "get_device_info": "Get FPGA device information"
        }
        
        # Initialize firmware manager
        self.firmware_mgr = FirmwareManager.Instance()
        
        # Store device information
        self.device_info = {}
        
        # Register default bitstream
        self._register_default_bitstream()

    def _register_default_bitstream(self):
        """Register the default iotsploit_func.bit bitstream with the firmware manager"""
        try:
            # Get the path to the gateware directory
            current_dir = Path(__file__).parent
            gateware_dir = current_dir / "gateware"
            bitstream_path = gateware_dir / "iotsploit_func.bit"
            
            if bitstream_path.exists():
                logger.info(f"Found default bitstream at {bitstream_path}")
                
                # Register with firmware manager
                self.firmware_mgr.add_firmware(
                    name="iotsploit_func",
                    path=str(bitstream_path),
                    device_type="fpga",
                    version="1.0.0",
                    flash_options={
                        "cable": "ft2232_b",  # Using ft2232_b as specified in the command
                        "target": "flash"     # Default to flash target
                    }
                )
                logger.info("Default bitstream registered with firmware manager")
            else:
                logger.warning(f"Default bitstream not found at {bitstream_path}")
        except Exception as e:
            logger.error(f"Error registering default bitstream: {str(e)}")

    def _scan_impl(self) -> List[Device]:
        """
        Scan for available ECP5 FPGA devices.
        This is a simplified implementation that returns a predefined device.
        In a real implementation, you would scan for actual hardware.
        """
        logger.info("Scanning for ECP5 FPGA devices")
        
        # For demonstration, we'll create a virtual device
        # In a real implementation, you would detect actual hardware
        devices = [
            Device(
                device_id="ecp5_001",
                name="Lattice ECP5",
                device_type=DeviceType.USB,  # Changed from Custom to USB
                attributes={
                    'description': 'Lattice ECP5 FPGA Development Board',
                    'cable': 'ft2232_b',  # Updated to match the command
                    'vendor_id': '0403',   # Added typical FTDI vendor ID
                    'product_id': '6010'   # Added typical FTDI product ID for FT2232
                }
            )
        ]
        
        if not devices:
            logger.warning("No ECP5 FPGA devices found")
        else:
            logger.info(f"Found {len(devices)} ECP5 FPGA device(s)")
            
        return devices

    def _initialize_impl(self, device: Device) -> bool:
        """
        Initialize the ECP5 FPGA device.
        """
        logger.info(f"Initializing ECP5 FPGA device: {device.device_id}")
        
        # Store device information for later use
        self.device_info[device.device_id] = {
            'cable': device.attributes.get('cable', 'ft2232_b'),  # Updated default
            'vendor_id': device.attributes.get('vendor_id', '0403'),  # Added vendor ID
            'product_id': device.attributes.get('product_id', '6010')  # Added product ID
        }
        
        # Check if openFPGALoader is available
        if not shutil.which('openFPGALoader'):
            logger.warning("openFPGALoader not found in PATH. Please install it")
            return False
            
        logger.info(f"ECP5 FPGA device {device.device_id} initialized successfully")
        return True

    def _connect_impl(self, device: Device) -> bool:
        """
        Connect to the ECP5 FPGA device.
        For FPGA devices, this might just verify communication.
        """
        logger.info(f"Connecting to ECP5 FPGA device: {device.device_id}")
        
        # For FPGAs, connection might just be a verification step
        # or setting up communication channels
        
        # Simulate connection verification
        if device.device_id in self.device_info:
            logger.info(f"ECP5 FPGA device {device.device_id} connected successfully")
            return True
        else:
            logger.error(f"Device {device.device_id} not initialized")
            return False

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Optional[Any]:
        """
        Execute commands on the ECP5 FPGA device.
        """
        if device.device_id not in self.device_info:
            logger.error(f"Device {device.device_id} not initialized")
            raise RuntimeError("Device not initialized")
            
        args = args or {}
        
        # Command dispatch
        if command == "flash_firmware":
            return self._handle_flash_firmware(device, args)
        elif command == "load_bitstream":
            return self._handle_load_bitstream(device, args)
        elif command == "flash_bitstream":
            return self._handle_flash_bitstream(device, args)
        elif command == "get_device_info":
            return self._handle_get_device_info(device, args)
        else:
            logger.error(f"Unknown command: {command}")
            return f"Unknown command: {command}"

    def _handle_flash_firmware(self, device: Device, args: Dict) -> Dict:
        """Handle flash_firmware command"""
        firmware_name = args.get('firmware_name', 'iotsploit_func')  # Default to iotsploit_func
        options = args.get('options', {})
        
        # Get device attributes to use as default options
        device_attrs = self.device_info.get(device.device_id, {})
        
        # Merge device attributes with provided options
        flash_options = {
            'cable': device_attrs.get('cable', 'ft2232_b'),  # Updated default
        }
        flash_options.update(options)
        
        # Determine if we're loading to SRAM or flashing to configuration memory
        target = options.get('target', 'flash').lower()  # Default to flash
        
        try:
            if target == 'sram':
                # Load to SRAM (temporary)
                result = self.firmware_mgr.load_fpga_bitstream(firmware_name, flash_options)
                action = "loaded to SRAM"
            else:
                # Flash to configuration memory (permanent)
                result = self.firmware_mgr.flash_fpga_bitstream(firmware_name, flash_options)
                action = "flashed to configuration memory"
                
            if result:
                return {
                    "status": "success", 
                    "message": f"Firmware {firmware_name} successfully {action}"
                }
            else:
                return {
                    "status": "error", 
                    "message": f"Failed to {action.split()[0]} firmware {firmware_name}"
                }
        except Exception as e:
            logger.error(f"Error flashing firmware: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _handle_load_bitstream(self, device: Device, args: Dict) -> Dict:
        """Handle load_bitstream command (to SRAM)"""
        firmware_name = args.get('firmware_name', 'iotsploit_func')  # Default to iotsploit_func
        options = args.get('options', {})
        
        # Get device attributes to use as default options
        device_attrs = self.device_info.get(device.device_id, {})
        
        # Merge device attributes with provided options
        load_options = {
            'cable': device_attrs.get('cable', 'ft2232_b'),  # Updated default
            'target': 'sram'  # Ensure target is set to SRAM
        }
        load_options.update(options)
        
        try:
            result = self.firmware_mgr.load_fpga_bitstream(firmware_name, load_options)
            if result:
                return {
                    "status": "success", 
                    "message": f"Bitstream {firmware_name} successfully loaded to SRAM"
                }
            else:
                return {
                    "status": "error", 
                    "message": f"Failed to load bitstream {firmware_name} to SRAM"
                }
        except Exception as e:
            logger.error(f"Error loading bitstream: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _handle_flash_bitstream(self, device: Device, args: Dict) -> Dict:
        """Handle flash_bitstream command (to configuration flash)"""
        firmware_name = args.get('firmware_name', 'iotsploit_func')  # Default to iotsploit_func
        options = args.get('options', {})
        
        # Get device attributes to use as default options
        device_attrs = self.device_info.get(device.device_id, {})
        
        # Merge device attributes with provided options
        flash_options = {
            'cable': device_attrs.get('cable', 'ft2232_b'),  # Updated default
            'target': 'flash',  # Ensure target is set to flash
            'verify': args.get('verify', True)  # Default to verify
        }
        flash_options.update(options)
        
        try:
            result = self.firmware_mgr.flash_fpga_bitstream(firmware_name, flash_options)
            if result:
                return {
                    "status": "success", 
                    "message": f"Bitstream {firmware_name} successfully flashed to configuration memory"
                }
            else:
                return {
                    "status": "error", 
                    "message": f"Failed to flash bitstream {firmware_name} to configuration memory"
                }
        except Exception as e:
            logger.error(f"Error flashing bitstream: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _handle_get_device_info(self, device: Device, args: Dict) -> Dict:
        """Handle get_device_info command"""
        device_info = self.device_info.get(device.device_id, {})
        return {
            "status": "success",
            "device_id": device.device_id,
            "name": device.name,
            "cable": device_info.get('cable', 'ft2232_b'),  # Updated default
            "vendor_id": device_info.get('vendor_id', '0403'),  # Added vendor ID
            "product_id": device_info.get('product_id', '6010'),  # Added product ID
            "default_bitstream": "iotsploit_func.bit"
        }

    def _reset_impl(self, device: Device) -> bool:
        """
        Reset the ECP5 FPGA device.
        """
        logger.info(f"Resetting ECP5 FPGA device: {device.device_id}")
        
        # For FPGAs, reset might involve reloading a default bitstream
        # or triggering a hardware reset signal
        
        # Simplified implementation
        return True

    def _close_impl(self, device: Device) -> bool:
        """
        Close the connection to the ECP5 FPGA device.
        """
        logger.info(f"Closing ECP5 FPGA device: {device.device_id}")
        
        # Clean up any resources
        if device.device_id in self.device_info:
            del self.device_info[device.device_id]
            
        return True

    def _acquisition_loop(self):
        """
        Data acquisition loop - not used for this driver.
        """
        # FPGA devices typically don't have continuous data acquisition
        # unless specifically configured for streaming data
        while self.is_acquiring.is_set():
            time.sleep(1)  # Just sleep to keep the thread alive

    def _setup_acquisition(self, device: Device):
        """Setup for data acquisition - not used for this driver."""
        pass

    def _cleanup_acquisition(self, device: Device):
        """Cleanup after data acquisition - not used for this driver."""
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test the driver
    driver = ECP5FPGADriver()
    devices = driver.scan()
    
    if devices:
        test_device = devices[0]
        print(f"ECP5 FPGA Device Found: {test_device}")

        try:
            if driver.initialize(test_device):
                if driver.connect(test_device):
                    print("Device connected successfully")
                    
                    # Test flash_firmware command with default bitstream
                    result = driver.command(test_device, "flash_firmware")
                    print(f"Flash firmware result: {result}")
                    
                    # Test get_device_info command
                    info = driver.command(test_device, "get_device_info")
                    print(f"Device info: {info}")
                    
                    if driver.close(test_device):
                        print("Device closed successfully")
                    else:
                        print("Failed to close device")
                else:
                    print("Failed to connect to device")
        except Exception as ex:
            print(f"Error during device operation: {ex}")
    else:
        print("No ECP5 FPGA devices found")