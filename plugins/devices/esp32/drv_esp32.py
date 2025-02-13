import logging
from typing import Optional, Dict, List
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, SerialDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.scpi_client.transport import ScpiSerialTransport
from sat_toolkit.scpi_client.client import ScpiClient
import time

logger = logging.getLogger(__name__)

class ESP32Driver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.transport = None
        self.client = None
        # Define supported commands
        self.supported_commands = {
            "scan_wifi": "Scan for available WiFi networks",
            "get_version": "Get device version",
            "get_status": "Get device status",
            "reset": "Reset the ESP32 device",
            "start_wifi_monitor": "Start continuous WiFi monitoring",
            "stop_wifi_monitor": "Stop continuous WiFi monitoring"
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
        Scan for available ESP32 devices.
        """
        device = SerialDevice(
            device_id="esp32_001",
            name="ESP32",
            port='/dev/ttyUSB3',
            baud_rate=115200,
            attributes={
                'description': 'ESP32 Development Board',
            }
        )
        return [device]

    def _initialize_impl(self, device: SerialDevice) -> bool:
        """
        Initialize the ESP32 device using SCPI over serial.
        """
        if device.device_type != DeviceType.Serial:
            raise ValueError("This plugin only supports serial devices")
        
        logger.info(f"Initializing ESP32 device on port {device.port}")
        try:
            self.transport = ScpiSerialTransport(
                port=device.port,
                baudrate=device.baud_rate,
                timeout=1.0
            )
            self.client = ScpiClient(self.transport)
            logger.info("ESP32 device initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ESP32 device: {e}")
            raise

    def _connect_impl(self, device: SerialDevice) -> bool:
        """
        Connect to the ESP32 device using SCPI client.
        """
        if not self.client:
            logger.error("Device not initialized. Please initialize first.")
            raise RuntimeError("Device not initialized")
        
        try:
            self.client.connect()
            version = self.client.get_version()
            status = self.client.get_status()
            logger.info(f"ESP32 device connected successfully. Version: {version}, Status: {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ESP32 device: {e}")
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

    def _command_impl(self, device: SerialDevice, command: str, args: Optional[Dict] = None) -> Optional[str]:
        """
        Execute commands on the ESP32 device using SCPI.
        Uses a dictionary dispatch for cleaner code.
        """
        if not self.client:
            logger.error("Cannot send command: ESP32 device not connected")
            raise RuntimeError("Device not connected")
        
        command_map = {
            "scan_wifi": self._handle_scan_wifi,
            "start_wifi_monitor": self._handle_start_wifi_monitor,
            "stop_wifi_monitor": self._handle_stop_wifi_monitor,
            "get_version": self._handle_get_version,
            "get_status": self._handle_get_status,
            "reset": self._handle_reset
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
        Reset the ESP32 device using SCPI *RST command.
        """
        try:
            if self.client:
                self.client.send_command("*RST")
                logger.info("ESP32 device reset successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reset ESP32 device: {e}")
            raise

    def _close_impl(self, device: SerialDevice) -> bool:
        """
        Close the connection to the ESP32 device.
        """
        try:
            if self.is_acquiring.is_set():
                self.stop_streaming(device)
            if self.client:
                self.client.close()
            self.transport = None
            self.client = None
            logger.info("ESP32 device closed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to close ESP32 device: {e}")
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
        print(f"ESP32 Device Found: {test_device}")

        try:
            if driver.initialize(test_device):
                if driver.connect(test_device):
                    print("Device connected successfully")
                    
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
        print("No ESP32 devices found")