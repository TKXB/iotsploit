import socket
import struct
import threading
import time
import logging
import uuid
import can
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, SocketCANDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamType

logger = logging.getLogger(__name__)

class SocketCANDriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.supported_commands = {
            "start": "Start monitoring/receiving CAN messages",
            "stop": "Stop monitoring/receiving CAN messages",
            "dump": "Display current CAN interface status and state",
            "send": "Send a test CAN message with ID 0x123 and data DEADBEEF"
        }

    def receiver_thread_fn(self):
        while self.running.is_set():
            try:
                message = self.bus.recv(timeout=0.1)
                if not self.running.is_set():
                    break
                if message:
                    stream_data = StreamData(
                        stream_type=StreamType.CAN,
                        channel=self.device.device_id,
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
                    self.stream_wrapper.broadcast_data(stream_data)
                    logger.info(f"Received and broadcast CAN message - ID: {hex(message.arbitration_id)}, "
                              f"Data: {message.data.hex()}, DLC: {message.dlc}")
            except Exception as e:
                logger.error(f"Error receiving CAN message: {str(e)}")
                time.sleep(0.1)

    def shutdown_bus(self):
        """CAN-specific bus shutdown"""
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")

    def setup_bus(self):
        """CAN-specific bus setup"""
        self.bus = can.interface.Bus(channel=self.current_interface, 
                                   bustype='socketcan')

    def scan(self):
        try:
            logger.info("Starting scan for SocketCAN interfaces...")
            import subprocess
            devices = []
            seen_interfaces = set()
            
            result = subprocess.run(['ip', 'link', 'show'], 
                                 capture_output=True, text=True)
            
            logger.debug(f"Command output: {result.stdout}")
            
            for line in result.stdout.splitlines():
                if (':' in line) and ('can' in line or 'vcan' in line):
                    parts = line.split(':')
                    if len(parts) > 1:
                        interface = parts[1].strip()
                        
                        if interface in seen_interfaces:
                            continue
                        seen_interfaces.add(interface)
                        
                        logger.info(f"Found CAN interface: {interface}")
                        
                        interface_num = int(''.join(filter(str.isdigit, interface))) + 1
                        prefix = 'vcan_' if interface.startswith('vcan') else 'can_'
                        device_id = f"{prefix}{str(interface_num).zfill(3)}"
                        
                        is_virtual = interface.startswith('vcan')
                        
                        device = SocketCANDevice(
                            device_id=device_id,
                            name=f"SocketCAN_{interface}",
                            interface=interface,
                            attributes={
                                'description': 'Virtual SocketCAN Interface' if is_virtual else 'SocketCAN Interface',
                                'type': 'CAN',
                                'bitrate': 500000,
                                'is_virtual': is_virtual
                            }
                        )
                        logger.debug(f"Created device object: {device.name} (ID: {device.device_id})")
                        devices.append(device)
            
            logger.info(f"Scan complete. Found {len(devices)} SocketCAN interfaces")
            return devices
        except Exception as e:
            logger.error(f"Error scanning for CAN interfaces: {str(e)}")
            logger.debug("Scan failed with exception", exc_info=True)
            return []

    def initialize(self, device: SocketCANDevice):
        if not isinstance(device, SocketCANDevice):
            raise ValueError("This plugin only supports SocketCAN devices")
        
        logger.info(f"Initializing SocketCAN device on interface {device.interface}")
        try:
            import subprocess
            is_virtual = device.attributes.get('is_virtual', False)
            
            if not is_virtual:
                subprocess.run(['sudo', 'ip', 'link', 'set', device.interface, 'type', 'can', 
                              'bitrate', str(device.attributes.get('bitrate', 500000))])
            
            subprocess.run(['sudo', 'ip', 'link', 'set', device.interface, 'up'])
            
            self.current_interface = device.interface
            self.device = device
            self.connected = True
            logger.info(f"{'Virtual ' if is_virtual else ''}SocketCAN device initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SocketCAN device: {e}")
            return False

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

    def command(self, device: SocketCANDevice, command: str):
        logger.debug(f"Received command: '{command}'")
        if not self.bus and command.lower() != "start":
            logger.error("Cannot execute command: SocketCAN device not connected")
            return

        try:
            command = command.lower()
            if command == "start":
                self.start_monitoring(device)
            
            elif command == "stop":
                self.stop_monitoring(device)
            
            elif command == "dump":
                logger.info(f"CAN Interface Status - Running: {self.running.is_set()}, "
                          f"Interface: {self.current_interface}")
            
            elif command == "send":
                test_id = 0x123
                test_data = bytes.fromhex("DEADBEEF")
                self.send_can_message(device, test_id, test_data)
                logger.info("Test CAN message sent")
            
            else:
                logger.error(f"Unknown command: {command}. Valid commands are: {', '.join(self.supported_commands.keys())}")
                
        except Exception as e:
            logger.error(f"Failed to execute command {command}: {e}")

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

    def close(self, device: SocketCANDevice):
        try:
            self.stop_receiver()
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

    def validate_can_message(self, can_id: int, data: bytes) -> bool:
        try:
            if not (0 <= can_id <= 0x7FF) and not (0 <= can_id <= 0x1FFFFFFF):
                logger.error(f"Invalid CAN ID: {hex(can_id)}")
                return False
            
            if len(data) > 8:
                logger.error(f"Invalid data length: {len(data)}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error validating CAN message: {e}")
            return False

    def send_can_message(self, device: SocketCANDevice, can_id: int, data: bytes):
        if not self.bus:
            raise RuntimeError("Cannot send message: SocketCAN device not connected")

        if not self.validate_can_message(can_id, data):
            raise ValueError("Invalid CAN message parameters")

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
            raise 

    def start_monitoring(self, device):
        """Override start_monitoring to include CAN-specific bus setup"""
        self.stop_receiver()
        self.setup_bus()  # CAN-specific setup
        logger.info("Starting message monitoring")
        channel = device.device_id
        self.stream_wrapper.register_stream(channel)
        self.start_receiver()

    def stop_monitoring(self, device):
        """Override stop_monitoring to include CAN-specific bus shutdown"""
        channel = device.device_id
        self.stream_wrapper.unregister_stream(channel)
        self.stream_wrapper.stop_broadcast(channel)
        self.stop_receiver()
        self.shutdown_bus()  # CAN-specific shutdown
        self.bus = None

    def setup_bus(self):
        """CAN-specific bus setup"""
        self.bus = can.interface.Bus(channel=self.current_interface, 
                                   bustype='socketcan')

    def shutdown_bus(self):
        """CAN-specific bus shutdown"""
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}") 