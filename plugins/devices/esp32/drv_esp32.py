import erpc
from erpc.transport import SerialTransport
from erpc.client import ClientManager
from generated.esp32_service_ap.client import APServiceClient
import threading
import time
import logging
import pluggy
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, SerialDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
import uuid

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("device_mgr")

class ESP32Driver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.transport = None
        self.client_manager = None
        self.server = None
        self.client_thread = None
        self.client = None

    def client_thread_fn(self):
        self.client = APServiceClient(self.client_manager)
        i = 0
        while True:
            logger.debug(f"Calling getApList ({i})...")
            try:
                ap_list = self.client.getApList()
                i = i + 1
                
                if ap_list:
                    for ap in ap_list:
                        logger.info(f"AP Found - SSID: {ap.ssid}, BSSID: {ap.bssid}, "
                                  f"Channel: {ap.primary}, RSSI: {ap.rssi} dBm")
                else:
                    logger.warning("No access points found or invalid data received")
                
            except Exception as e:
                logger.error(f"Error during RPC call: {str(e)}")
                logger.error(f"Error type: {type(e)}")
            
            time.sleep(1)

    @hookimpl
    def scan(self):
        # In a real implementation, you might want to scan available serial ports
        # For now, we'll return a predefined device
        device = SerialDevice(
            device_id=str(uuid.uuid4()),
            name="ESP32",
            port='/dev/ttyUSB1',
            baud_rate=115200,
            attributes={
                'description': 'ESP32 Development Board',
            }
        )
        return [device]

    @hookimpl
    def initialize(self, device: SerialDevice):
        if device.device_type != DeviceType.SERIAL:
            raise ValueError("This plugin only supports serial devices")
        
        logger.info(f"Initializing ESP32 device on port {device.port}")
        try:
            self.transport = SerialTransport(device.port, device.baud_rate)
            arbitrator = erpc.arbitrator.TransportArbitrator(
                self.transport, erpc.basic_codec.BasicCodec())
            
            self.client_manager = ClientManager(
                arbitrator.shared_transport, 
                erpc.basic_codec.BasicCodec
            )
            self.client_manager.arbitrator = arbitrator
            
            self.server = erpc.simple_server.SimpleServer(
                arbitrator, 
                erpc.basic_codec.BasicCodec
            )
            
            logger.info("ESP32 device initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ESP32 device: {e}")
            return False

    @hookimpl
    def connect(self, device: SerialDevice):
        if not self.client_manager:
            logger.error("Device not initialized. Please initialize first.")
            return False

        try:
            self.client_thread = threading.Thread(
                target=self.client_thread_fn,
                name='ESP32_CLIENT'
            )
            self.client_thread.daemon = True
            self.client_thread.start()
            
            logger.info(f"ESP32 device connected successfully on {device.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ESP32 device: {e}")
            return False

    @hookimpl
    def execute(self, device: SerialDevice, target: str):
        if self.client:
            logger.info(f"Executing {target} on ESP32 device")
            # Implement specific execution logic here
            pass

    @hookimpl
    def send_command(self, device: SerialDevice, command: str):
        if self.client:
            logger.info(f"Sending command '{command}' to ESP32 device")
            # Implement command sending logic here
            pass
        else:
            logger.error("Cannot send command: ESP32 device not connected")

    @hookimpl
    def reset(self, device: SerialDevice):
        if self.transport:
            try:
                # Implement reset logic here
                logger.info("ESP32 device reset successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to reset ESP32 device: {e}")
                return False

    @hookimpl
    def close(self, device: SerialDevice):
        try:
            if self.transport:
                self.transport.close()
            if self.client_thread and self.client_thread.is_alive():
                # Implement proper thread termination
                pass
            
            self.transport = None
            self.client_manager = None
            self.server = None
            self.client = None
            
            logger.info("ESP32 device closed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to close ESP32 device: {e}")
            return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    ability = ESP32Driver()
    found_devices = ability.scan()
    
    if found_devices:
        test_device = found_devices[0]
        print(f"ESP32 Device Found: {test_device}")
        
        if ability.initialize(test_device):
            if ability.connect(test_device):
                print("Device connected successfully")
                # Perform some operations here
                ability.send_command(test_device, "test_command")
                time.sleep(5)  # Let it run for a bit
                
                if ability.close(test_device):
                    print("Device closed successfully")
                else:
                    print("Failed to close device")
            else:
                print("Failed to connect to device")
    else:
        print("No ESP32 devices found")