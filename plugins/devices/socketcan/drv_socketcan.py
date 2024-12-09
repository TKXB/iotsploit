import socket
import struct
import threading
import time
import logging
import pluggy
import uuid
import can
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType
from sat_toolkit.core.base_plugin import BaseDeviceDriver

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("device_mgr")

class SocketCANDevice(Device):
    def __init__(self, device_id: str, name: str, interface: str, attributes: dict):
        super().__init__(device_id, name, DeviceType.Ethernet, attributes)
        self.interface = interface

class SocketCANDriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.bus = None
        self.receiver_thread = None
        self.running = False
        self.current_interface = None

    def receiver_thread_fn(self):
        while self.running:
            try:
                message = self.bus.recv(timeout=1.0)
                if message:
                    logger.info(f"Received CAN message - ID: {hex(message.arbitration_id)}, "
                              f"Data: {message.data.hex()}, DLC: {message.dlc}")
            except Exception as e:
                logger.error(f"Error receiving CAN message: {str(e)}")
                time.sleep(0.1)

    @hookimpl
    def scan(self):
        try:
            logger.info("Starting scan for SocketCAN interfaces...")
            # Check for available CAN interfaces
            import subprocess
            logger.debug("Running 'ip link show type can' command")
            result = subprocess.run(['ip', 'link', 'show', 'type', 'can'], 
                                 capture_output=True, text=True)
            
            devices = []
            logger.debug(f"Command output: {result.stdout}")
            
            for line in result.stdout.splitlines():
                if 'can' in line and ':' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        interface = parts[1].strip()
                        logger.info(f"Found CAN interface: {interface}")
                        device = SocketCANDevice(
                            device_id=str(uuid.uuid4()),
                            name=f"SocketCAN_{interface}",
                            interface=interface,
                            attributes={
                                'description': 'SocketCAN Interface',
                                'type': 'CAN',
                                'bitrate': 500000  # Default bitrate
                            }
                        )
                        logger.debug(f"Created device object: {device.name} (ID: {device.device_id})")
                        devices.append(device)
                    else:
                        logger.warning(f"Unexpected line format: {line}")
            
            logger.info(f"Scan complete. Found {len(devices)} SocketCAN interfaces")
            return devices
        except Exception as e:
            logger.error(f"Error scanning for CAN interfaces: {str(e)}")
            logger.debug("Scan failed with exception", exc_info=True)
            return []

    @hookimpl
    def initialize(self, device: SocketCANDevice):
        if not isinstance(device, SocketCANDevice):
            raise ValueError("This plugin only supports SocketCAN devices")
        
        logger.info(f"Initializing SocketCAN device on interface {device.interface}")
        try:
            # Configure the CAN interface
            import subprocess
            subprocess.run(['sudo', 'ip', 'link', 'set', device.interface, 'type', 'can', 
                          'bitrate', str(device.attributes.get('bitrate', 500000))])
            subprocess.run(['sudo', 'ip', 'link', 'set', device.interface, 'up'])
            
            self.current_interface = device.interface
            logger.info("SocketCAN device initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SocketCAN device: {e}")
            return False

    @hookimpl
    def connect(self, device: SocketCANDevice):
        if not self.current_interface:
            logger.error("Device not initialized. Please initialize first.")
            return False

        try:
            self.bus = can.interface.Bus(channel=self.current_interface, 
                                       bustype='socketcan')
            self.running = True
            self.receiver_thread = threading.Thread(
                target=self.receiver_thread_fn,
                name='SOCKETCAN_RECEIVER'
            )
            self.receiver_thread.daemon = True
            self.receiver_thread.start()
            
            logger.info(f"SocketCAN device connected successfully on {device.interface}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SocketCAN device: {e}")
            return False

    @hookimpl
    def command(self, device: SocketCANDevice, command: str):
        if not self.bus:
            logger.error("Cannot execute command: SocketCAN device not connected")
            return

        try:
            command = command.lower()
            if command == "start":
                # Start monitoring/receiving CAN messages
                if not self.running:
                    self.running = True
                    self.receiver_thread = threading.Thread(
                        target=self.receiver_thread_fn,
                        name='SOCKETCAN_RECEIVER'
                    )
                    self.receiver_thread.daemon = True
                    self.receiver_thread.start()
                    logger.info("Started CAN message monitoring")
            
            elif command == "stop":
                # Stop monitoring/receiving CAN messages
                self.running = False
                if self.receiver_thread and self.receiver_thread.is_alive():
                    self.receiver_thread.join(timeout=1.0)
                logger.info("Stopped CAN message monitoring")
            
            elif command == "dump":
                # This command would typically return the current state or message buffer
                # For now, just log the current state
                logger.info(f"CAN Interface Status - Running: {self.running}, "
                          f"Interface: {self.current_interface}")
            
            elif command == "send":
                # Send a test CAN message with ID 0x123 and data DEADBEEF
                test_id = 0x123
                test_data = bytes.fromhex("DEADBEEF")
                self.send_can_message(device, test_id, test_data)
                logger.info("Test CAN message sent")
            
            else:
                logger.error(f"Unknown command: {command}. Valid commands are: start, stop, dump, send")
                
        except Exception as e:
            logger.error(f"Failed to execute command {command}: {e}")

    @hookimpl
    def reset(self, device: SocketCANDevice):
        if self.current_interface:
            try:
                import subprocess
                subprocess.run(['sudo', 'ip', 'link', 'set', self.current_interface, 'down'])
                subprocess.run(['sudo', 'ip', 'link', 'set', self.current_interface, 'up'])
                logger.info("SocketCAN device reset successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to reset SocketCAN device: {e}")
                return False

    @hookimpl
    def close(self, device: SocketCANDevice):
        try:
            self.running = False
            if self.bus:
                self.bus.shutdown()
            if self.receiver_thread and self.receiver_thread.is_alive():
                self.receiver_thread.join(timeout=1.0)
            
            if self.current_interface:
                import subprocess
                subprocess.run(['sudo', 'ip', 'link', 'set', self.current_interface, 'down'])
            
            self.bus = None
            self.current_interface = None
            
            logger.info("SocketCAN device closed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to close SocketCAN device: {e}")
            return False

    # Add a new method for sending actual CAN messages
    def send_can_message(self, device: SocketCANDevice, can_id: int, data: bytes):
        if not self.bus:
            logger.error("Cannot send message: SocketCAN device not connected")
            return

        try:
            message = can.Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=False
            )
            self.bus.send(message)
            logger.info(f"Sent CAN message - ID: {hex(message.arbitration_id)}, "
                       f"Data: {message.data.hex()}")
        except Exception as e:
            logger.error(f"Failed to send CAN message: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    driver = SocketCANDriver()
    found_devices = driver.scan()
    
    if found_devices:
        test_device = found_devices[0]
        print(f"SocketCAN Device Found: {test_device}")
        
        if driver.initialize(test_device):
            if driver.connect(test_device):
                print("Device connected successfully")
                # Test the new command structure
                driver.command(test_device, "start")
                time.sleep(1)
                # Send a test message using the new method
                driver.send_can_message(test_device, 0x123, bytes.fromhex("DEADBEEF"))
                time.sleep(3)
                driver.command(test_device, "dump")
                driver.command(test_device, "stop")
                
                if driver.close(test_device):
                    print("Device closed successfully")
                else:
                    print("Failed to close device")
            else:
                print("Failed to connect to device")
    else:
        print("No SocketCAN devices found") 