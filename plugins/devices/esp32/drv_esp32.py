import logging
from typing import Optional, Dict, List
from iotsploit_core.domain.device import Device, DeviceType, SerialDevice
from iotsploit_core.core.base_plugin import BaseDeviceDriver
from scpi_client import ScpiClient, ScpiSerialTransport
from iotsploit_core.core.tool_service import get_firmware_service
import time
import serial.tools.list_ports
from pathlib import Path

logger = logging.getLogger(__name__)

class ESP32Driver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.transport = None
        self.client = None
        # Initialize firmware tool service
        self.firmware_service = get_firmware_service()
        # Define supported commands
        self.supported_commands = {
            "scan_wifi": "Scan for available WiFi networks",
            "get_version": "Get device version",
            "get_status": "Get device status",
            "reset": "Reset the ESP32 device",
            "start_wifi_monitor": "Start continuous WiFi monitoring",
            "stop_wifi_monitor": "Stop continuous WiFi monitoring",
            "flash_firmware": "Flash firmware to ESP32-S3 device",
            "erase_flash": "Erase ESP32-S3 flash memory",
            "get_chip_info": "Get ESP32-S3 chip information"
        }

    def get_auth_mode_str(self, auth_mode):
        """Convert auth mode number to string description."""
        auth_modes = {
            0: "OPEN",
            1: "WEP",
            2: "WPA_PSK",
            3: "WPA2_PSK",
            4: "WPA_WPA2_PSK",
            5: "WPA2_ENTERPRISE",
            6: "WPA3_PSK",
            7: "WPA2_WPA3_PSK"
        }
        return auth_modes.get(int(auth_mode), f"UNKNOWN({auth_mode})")

    def _scan_wifi_networks(self) -> List[Dict]:
        """Scan for WiFi networks and return formatted results."""
        ap_list = self.client.query("WIFi:AP:LIST?", timeout=10.0)
        if not ap_list or ap_list == "NO_AP_FOUND" or ap_list.startswith("ERROR"):
            logger.info("No WiFi networks found or error response received from client")
            return []

        result = []
        ap_entries = [ap for ap in ap_list.strip().split(';') if ap]
        for ap in ap_entries:
            try:
                ssid, rssi, channel, auth = ap.split(',')
                security = self.get_auth_mode_str(auth)
                logger.info("Found WiFi Network: SSID: %s, RSSI: %s dBm, Channel: %s, Security: %s",
                            ssid, rssi, channel, security)
                result.append({
                    "ssid": ssid,
                    "rssi": f"{rssi} dBm",
                    "channel": channel,
                    "security": security
                })
            except ValueError as e:
                logger.error("Error parsing AP entry: %s - %s", ap, str(e))
        return result

    def _scan_impl(self) -> List[Device]:
        """
        Scan for available ESP32-S3 devices by checking all CP210x devices.
        Returns the device with correct version number.
        """
        devices = []
        # Find all CP210x devices
        for port in serial.tools.list_ports.comports():
            if "CP210" in port.description:
                logger.info(f"Found CP210x device at {port.device}")
                try:
                    # Try to connect and check version
                    temp_transport = ScpiSerialTransport(
                        port=port.device,
                        baudrate=115200,
                        timeout=1.0
                    )
                    temp_client = ScpiClient(temp_transport)
                    temp_client.connect()
                    
                    try:
                        version = temp_client.get_version()
                        if version.strip() == "1.0.0":
                            logger.info(f"Found ESP32-S3 device at {port.device} with correct version")
                            devices.append(SerialDevice(
                                device_id="esp32s3_001",
                                name="ESP32-S3",
                                port=port.device,
                                baud_rate=115200,
                                attributes={
                                    'description': 'ESP32-S3 Development Board',
                                    'serial_number': port.serial_number,
                                    'chip': 'esp32s3'
                                }
                            ))
                    except Exception as e:
                        logger.debug(f"Not an ESP32-S3 device at {port.device}: {e}")
                    
                    temp_client.close()
                except Exception as e:
                    logger.debug(f"Failed to check device at {port.device}: {e}")
                    continue

        if not devices:
            logger.warning("No ESP32-S3 devices found")
        return devices

    def _initialize_impl(self, device: SerialDevice) -> bool:
        """
        Initialize the ESP32-S3 device using SCPI over serial.
        """
        if device.device_type != DeviceType.Serial:
            raise ValueError("This plugin only supports serial devices")
        
        logger.info(f"Initializing ESP32-S3 device on port {device.port}")
        try:
            self.transport = ScpiSerialTransport(
                port=device.port,
                baudrate=device.baud_rate,
                timeout=1.0
            )
            self.client = ScpiClient(self.transport)
            logger.info("ESP32-S3 device initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ESP32-S3 device: {e}")
            raise

    def _connect_impl(self, device: SerialDevice) -> bool:
        """
        Connect to the ESP32-S3 device using SCPI client.
        """
        if not self.client:
            logger.error("Device not initialized. Please initialize first.")
            raise RuntimeError("Device not initialized")
        
        try:
            self.client.connect()
            version = self.client.get_version()
            status = self.client.get_status()
            logger.info(f"ESP32-S3 device connected successfully. Version: {version}, Status: {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ESP32-S3 device: {e}")
            raise

    def _acquisition_loop(self):
        """Continuous WiFi scanning loop."""
        while self.is_acquiring.is_set():
            try:
                wifi_list = self._scan_wifi_networks()
                # Send data through stream manager
                if wifi_list:
                    for device_id in self._devices:
                        self.stream_wrapper.broadcast_data(device_id, {
                            "type": "wifi_scan",
                            "timestamp": time.time(),
                            "data": wifi_list
                        })
            except Exception as e:
                logger.error(f"Error in WiFi scanning loop: {e}")
            time.sleep(5)  # Scan every 5 seconds

    # --- Optimized command dispatch below ---

    def _handle_scan_wifi(self, device: SerialDevice, args: Optional[Dict] = None) -> Dict:
        wifi_list = self._scan_wifi_networks()
        return {
            "networks": wifi_list
        }

    def _handle_start_wifi_monitor(self, device: SerialDevice, args: Optional[Dict] = None) -> str:
        if not self.is_acquiring.is_set():
            self.start_streaming(device)
        return "WiFi monitoring started"

    def _handle_stop_wifi_monitor(self, device: SerialDevice, args: Optional[Dict] = None) -> str:
        if self.is_acquiring.is_set():
            self.stop_streaming(device)
        return "WiFi monitoring stopped"

    def _handle_get_version(self, device: SerialDevice, args: Optional[Dict] = None) -> str:
        return self.client.get_version()

    def _handle_get_status(self, device: SerialDevice, args: Optional[Dict] = None) -> str:
        return self.client.get_status()

    def _handle_reset(self, device: SerialDevice, args: Optional[Dict] = None) -> str:
        self.client.send_command("*RST")
        return "Device reset successfully"
        
    def _handle_flash_firmware(self, device: SerialDevice, args: Optional[Dict] = None) -> Dict:
        """
        Flash firmware to ESP32-S3 device using ESP32Programmer
        """
        try:
            # Check if esptool is available
            if not self.firmware_service.esp32.is_tool_available('esptool'):
                error_msg = "esptool is not available. Please install it: pip install esptool"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            # Get firmware name from args or use default
            firmware_name = args.get('firmware_name', 'esp32s3_wifi_penetration_tool') if args else 'esp32s3_wifi_penetration_tool'
            
            # Try to get firmware from the centralized manifest
            firmware_info = self.firmware_service.get_firmware_info(firmware_name)
            
            if not firmware_info:
                error_msg = f"Firmware '{firmware_name}' not found in manifest"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            # Get flash options from firmware config
            flash_options = firmware_info.get('flash_options', {})
            
            # Get port, chip, and baud from args or flash options or defaults
            port = args.get('port') if args else None
            port = port or flash_options.get('port', '/dev/ttyACM2')
            
            chip = args.get('chip') if args else None
            chip = chip or flash_options.get('chip', 'esp32s3')
            
            baud = args.get('baud') if args else None
            baud = baud or flash_options.get('baud', '460800')
            
            # Check if this firmware has a files array for multi-file flashing
            if 'files' in flash_options:
                # Use the files from the firmware configuration
                files = flash_options['files']
                logger.info(f"Using multi-file configuration from manifest: {len(files)} files")
                
                # Verify all files exist
                for file_entry in files:
                    file_path = file_entry['path']
                    if not Path(file_path).exists():
                        error_msg = f"Firmware file not found: {file_path}"
                        logger.error(error_msg)
                        return {"status": "error", "message": error_msg}
                
                logger.info(f"Flashing ESP32-S3 firmware '{firmware_name}' to {port}...")
                logger.info(f"Files to flash: {len(files)} files")
                
                # Flash all files in one operation using the ESP32 programmer
                result = self.firmware_service.esp32.flash_multi(
                    port=port,
                    files=files,
                    chip=chip,
                    baud=baud,
                    flash_mode=flash_options.get('flash_mode', 'dio'),
                    flash_freq=flash_options.get('flash_freq', '80m'),
                    flash_size=flash_options.get('flash_size', '2MB')
                )
            else:
                # Single file flashing
                firmware_path = firmware_info['path']
                if not Path(firmware_path).exists():
                    error_msg = f"Firmware file not found: {firmware_path}"
                    logger.error(error_msg)
                    return {"status": "error", "message": error_msg}
                
                logger.info(f"Flashing ESP32-S3 single firmware '{firmware_name}' to {port}...")
                
                result = self.firmware_service.esp32.flash_single(
                    port=port,
                    firmware_path=firmware_path,
                    address=flash_options.get('address', '0x10000'),
                    chip=chip,
                    baud=baud
                )
            
            if result.success:
                success_msg = f"ESP32-S3 firmware '{firmware_name}' flashed successfully in {result.execution_time:.2f}s"
                logger.info(success_msg)
                return {
                    "status": "success", 
                    "message": success_msg,
                    "execution_time": result.execution_time,
                    "firmware_name": firmware_name
                }
            else:
                error_msg = f"Failed to flash firmware '{firmware_name}': {result.stderr or 'Unknown error'}"
                logger.error(error_msg)
                return {
                    "status": "error", 
                    "message": error_msg,
                    "return_code": result.return_code,
                    "stderr": result.stderr
                }
                
        except Exception as e:
            error_msg = f"Error flashing ESP32-S3 firmware: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
    
    def _handle_erase_flash(self, device: SerialDevice, args: Optional[Dict] = None) -> Dict:
        """
        Erase ESP32-S3 flash memory using ESP32Programmer
        """
        try:
            if not self.firmware_service.esp32.is_tool_available('esptool'):
                error_msg = "esptool is not available. Please install it: pip install esptool"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            # Get port from args or use default
            port = args.get('port', '/dev/ttyACM2') if args else '/dev/ttyACM2'
            chip = args.get('chip', 'esp32s3') if args else 'esp32s3'
            baud = args.get('baud', '460800') if args else '460800'
            
            logger.info(f"Erasing ESP32-S3 flash on {port}...")
            
            result = self.firmware_service.esp32.erase_flash(
                port=port,
                chip=chip,
                baud=baud
            )
            
            if result.success:
                success_msg = f"ESP32-S3 flash erased successfully in {result.execution_time:.2f}s"
                logger.info(success_msg)
                return {
                    "status": "success", 
                    "message": success_msg,
                    "execution_time": result.execution_time
                }
            else:
                error_msg = f"Failed to erase flash: {result.stderr or 'Unknown error'}"
                logger.error(error_msg)
                return {
                    "status": "error", 
                    "message": error_msg,
                    "return_code": result.return_code,
                    "stderr": result.stderr
                }
                
        except Exception as e:
            error_msg = f"Error erasing ESP32-S3 flash: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
    
    def _handle_get_chip_info(self, device: SerialDevice, args: Optional[Dict] = None) -> Dict:
        """
        Get ESP32-S3 chip information using ESP32Programmer
        """
        try:
            if not self.firmware_service.esp32.is_tool_available('esptool'):
                error_msg = "esptool is not available. Please install it: pip install esptool"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            # Get port from args or use default
            port = args.get('port', '/dev/ttyACM2') if args else '/dev/ttyACM2'
            baud = args.get('baud', '460800') if args else '460800'
            
            logger.info(f"Getting ESP32-S3 chip info from {port}...")
            
            result = self.firmware_service.esp32.get_chip_info(
                port=port,
                baud=baud
            )
            
            if result.success:
                success_msg = f"ESP32-S3 chip info retrieved successfully"
                logger.info(success_msg)
                return {
                    "status": "success", 
                    "message": success_msg,
                    "chip_info": result.stdout,
                    "execution_time": result.execution_time
                }
            else:
                error_msg = f"Failed to get chip info: {result.stderr or 'Unknown error'}"
                logger.error(error_msg)
                return {
                    "status": "error", 
                    "message": error_msg,
                    "return_code": result.return_code,
                    "stderr": result.stderr
                }
                
        except Exception as e:
            error_msg = f"Error getting ESP32-S3 chip info: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    def _command_impl(self, device: SerialDevice, command: str, args: Optional[Dict] = None) -> Optional[str]:
        """
        Execute commands on the ESP32-S3 device using SCPI.
        Uses a dictionary dispatch for cleaner code.
        """
        if not self.client and command != "flash_firmware":
            logger.error("Cannot send command: ESP32-S3 device not connected")
            raise RuntimeError("Device not connected")
        
        command_map = {
            "scan_wifi": self._handle_scan_wifi,
            "start_wifi_monitor": self._handle_start_wifi_monitor,
            "stop_wifi_monitor": self._handle_stop_wifi_monitor,
            "get_version": self._handle_get_version,
            "get_status": self._handle_get_status,
            "reset": self._handle_reset,
            "flash_firmware": self._handle_flash_firmware,
            "erase_flash": self._handle_erase_flash,
            "get_chip_info": self._handle_get_chip_info
        }

        try:
            handler = command_map.get(command)
            if handler is None:
                logger.error(f"Unknown command: {command}")
                return f"Unknown command: {command}"
            return handler(device, args)
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            raise

    def _reset_impl(self, device: SerialDevice) -> bool:
        """
        Reset the ESP32-S3 device using SCPI *RST command.
        """
        try:
            if self.client:
                self.client.send_command("*RST")
                logger.info("ESP32-S3 device reset successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reset ESP32-S3 device: {e}")
            raise

    def _close_impl(self, device: SerialDevice) -> bool:
        """
        Close the connection to the ESP32-S3 device.
        """
        try:
            if self.is_acquiring.is_set():
                self.stop_streaming(device)
            if self.client:
                self.client.close()
            self.transport = None
            self.client = None
            logger.info("ESP32-S3 device closed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to close ESP32-S3 device: {e}")
            raise

    def _setup_acquisition(self, device: Device):
        """Setup for WiFi monitoring."""
        logger.info(f"Setting up WiFi monitoring for device {device.device_id}")

    def _cleanup_acquisition(self, device: Device):
        """Cleanup after WiFi monitoring."""
        logger.info(f"Cleaning up WiFi monitoring for device {device.device_id}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    driver = ESP32Driver()
    devices = driver.scan()
    
    if devices:
        test_device = devices[0]
        print(f"ESP32-S3 Device Found: {test_device}")

        try:
            if driver.initialize(test_device):
                if driver.connect(test_device):
                    print("Device connected successfully")
                    
                    # Test flash firmware command
                    result = driver.command(test_device, "flash_firmware")
                    print(f"Flash firmware result: {result}")
                    
                    # Start WiFi monitoring
                    result = driver.command(test_device, "start_wifi_monitor")
                    print(result)
                    
                    # Let it run for 30 seconds
                    time.sleep(30)
                    
                    # Stop WiFi monitoring
                    result = driver.command(test_device, "stop_wifi_monitor")
                    print(result)
                    
                    if driver.close(test_device):
                        print("Device closed successfully")
                    else:
                        print("Failed to close device")
                else:
                    print("Failed to connect to device")
        except Exception as ex:
            print(f"Error during device operation: {ex}")
    else:
        print("No ESP32-S3 devices found")
