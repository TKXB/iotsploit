import socket
import struct
import threading
import time
import logging
import pluggy
import uuid
import can
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, SocketCANDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
import asyncio
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamType

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("device_mgr")

class SocketCANDriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.bus = None
        self.receiver_thread = None
        self.running = threading.Event()
        self.current_interface = None
        self.stream_manager = StreamManager()
        self.device = None  # Store the connected device
        self.connected = False  # Connection status flag
        # Define commands with descriptions
        self.supported_commands = {
            "start": "Start monitoring/receiving CAN messages",
            "stop": "Stop monitoring/receiving CAN messages",
            "dump": "Display current CAN interface status and state",
            "send": "Send a test CAN message with ID 0x123 and data DEADBEEF"
        }

    def start_receiver(self):
        """Helper method to start the receiver thread if it's not already running"""
        if not self.running.is_set() and not (self.receiver_thread and self.receiver_thread.is_alive()):
            self.running.set()
            self.receiver_thread = threading.Thread(
                target=self.receiver_thread_fn,
                name='SOCKETCAN_RECEIVER'
            )
            self.receiver_thread.daemon = True
            self.receiver_thread.start()
            logger.info("Started CAN message monitoring")

    def stop_receiver(self):
        """Helper method to stop the receiver thread"""
        self.running.clear()
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")
        
        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=1.0)
            self.receiver_thread = None
        logger.info("Stopped CAN message monitoring")

    def receiver_thread_fn(self):
        while self.running.is_set():
            try:
                logger.debug(f"Receiver thread running state: {self.running.is_set()}")
                message = self.bus.recv(timeout=0.1)
                if not self.running.is_set():
                    break
                if message:
                    # Create StreamData object
                    stream_data = StreamData(
                        stream_type=StreamType.CAN,
                        channel=f"can_{self.current_interface}",
                        timestamp=time.time(),
                        data={
                            'id': hex(message.arbitration_id),
                            'data': message.data.hex(),
                            'dlc': message.dlc
                        },
                        metadata={
                            'interface': self.current_interface,
                            'is_extended_id': message.is_extended_id
                        }
                    )
                    
                    # Use asyncio to run the coroutine in the thread
                    asyncio.run(self.stream_manager.broadcast_data(stream_data))
                    
                    logger.info(f"Received and broadcast CAN message - ID: {hex(message.arbitration_id)}, "
                              f"Data: {message.data.hex()}, DLC: {message.dlc}")
            except Exception as e:
                logger.error(f"Error receiving CAN message: {str(e)}")
                time.sleep(0.1)

    @hookimpl
    def scan(self):
        try:
            logger.info("Starting scan for SocketCAN interfaces...")
            import subprocess
            devices = []
            
            # Check for both CAN and VCAN interfaces
            for interface_type in ['can', 'vcan']:
                logger.debug(f"Running 'ip link show type {interface_type}' command")
                result = subprocess.run(['ip', 'link', 'show', 'type', f'{interface_type}'], 
                                     capture_output=True, text=True)
                
                logger.debug(f"Command output for {interface_type}: {result.stdout}")
                
                for line in result.stdout.splitlines():
                    if ('can' in line or 'vcan' in line) and ':' in line:
                        parts = line.split(':')
                        if len(parts) > 1:
                            interface = parts[1].strip()
                            logger.info(f"Found {interface_type.upper()} interface: {interface}")
                            
                            # Determine if this is a virtual interface
                            is_virtual = interface_type == 'vcan'
                            
                            # Generate device_id to match devices.json format
                            if is_virtual:
                                device_id = "vcan_001"  # For virtual CAN
                            else:
                                # Extract number from can0, can1, etc and format as can_001, can_002
                                interface_num = int(interface.replace('can', '')) + 1
                                device_id = f"can_{str(interface_num).zfill(3)}"
                            
                            device = SocketCANDevice(
                                device_id=device_id,
                                name=f"SocketCAN_{interface}",
                                interface=interface,
                                attributes={
                                    'description': 'Virtual SocketCAN Interface' if is_virtual else 'SocketCAN Interface',
                                    'type': 'CAN',
                                    'bitrate': 500000,  # Default bitrate
                                    'is_virtual': is_virtual
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
            import subprocess
            # Check if it's a virtual interface
            is_virtual = device.attributes.get('is_virtual', False)
            
            if not is_virtual:  # Only configure bitrate for real CAN interfaces
                # Configure the CAN interface
                subprocess.run(['sudo', 'ip', 'link', 'set', device.interface, 'type', 'can', 
                              'bitrate', str(device.attributes.get('bitrate', 500000))])
            
            # Bring up the interface
            subprocess.run(['sudo', 'ip', 'link', 'set', device.interface, 'up'])
            
            self.current_interface = device.interface
            self.device = device
            self.connected = True
            logger.info(f"{'Virtual ' if is_virtual else ''}SocketCAN device initialized successfully")
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
            self.connected = True
            logger.info(f"SocketCAN device connected successfully on {device.interface}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SocketCAN device: {e}")
            return False

    @hookimpl
    def command(self, device: SocketCANDevice, command: str):
        logger.debug(f"Received command: '{command}'")
        if not self.bus and command.lower() != "start":
            logger.error("Cannot execute command: SocketCAN device not connected")
            return

        try:
            command = command.lower()
            if command == "start":
                # Ensure clean state before starting
                self.stop_receiver()
                # Create new bus connection
                self.bus = can.interface.Bus(channel=self.current_interface, 
                                           bustype='socketcan')
                logger.info("Starting CAN message monitoring")
                channel = f"can_{self.current_interface}"
                asyncio.run(self.stream_manager.register_stream(channel))
                self.start_receiver()
            
            elif command == "stop":
                channel = f"can_{self.current_interface}"
                asyncio.run(self.stream_manager.unregister_stream(channel))
                asyncio.run(self.stream_manager.stop_broadcast(channel))
                self.stop_receiver()
                self.bus = None  # Clear the bus reference
            
            elif command == "dump":
                # This command would typically return the current state or message buffer
                # For now, just log the current state
                logger.info(f"CAN Interface Status - Running: {self.running.is_set()}, "
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
            self.stop_receiver()  # Use the helper method
            if self.bus:
                self.bus.shutdown()
            
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

    def is_connected(self):
        return self.connected

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