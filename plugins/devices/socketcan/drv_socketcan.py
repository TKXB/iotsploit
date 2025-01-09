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
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamType, StreamSource, StreamAction
from sat_toolkit.tools.xlogger import xlog
from typing import Optional, Dict, List

logger = xlog.get_logger(__name__)

class SocketCANDriver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.bus = None
        self.current_interface = None
        self.supported_commands = {
            "start": "Start streaming CAN messages",
            "stop": "Stop streaming CAN messages",
            "dump": "Display current CAN interface status",
            "send": "Send a CAN message"
        }

    def _scan_impl(self) -> List[Device]:
        """扫描可用的CAN接口"""
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
            raise

    def _initialize_impl(self, device: SocketCANDevice) -> bool:
        """初始化CAN接口"""
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
            logger.info(f"{'Virtual ' if is_virtual else ''}SocketCAN device initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SocketCAN device: {e}")
            raise

    def _connect_impl(self, device: SocketCANDevice) -> bool:
        """连接到CAN接口"""
        if not self.current_interface:
            logger.error("Device not initialized. Please initialize first.")
            raise RuntimeError("Device not initialized")

        try:
            self.setup_bus()
            logger.info(f"Connected to SocketCAN device on {device.interface}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SocketCAN device: {e}")
            raise

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Optional[str]:
        """执行设备命令"""
        logger.debug(f"Received command: '{command}', args: {args}")
        try:
            command = command.lower()
            if command == "start":
                self.start_streaming(device)
                logger.info("Started CAN streaming")
                return "Started CAN streaming"
            
            elif command == "stop":
                self.stop_streaming(device)
                logger.info("Stopped CAN streaming")
                return "Stopped CAN streaming"
            
            elif command == "dump":
                status = {
                    "is_acquiring": self.is_acquiring.is_set(),
                    "interface": self.current_interface,
                    "bus_active": self.bus is not None
                }
                logger.info(f"CAN Interface Status: {status}")
                return str(status)
            
            elif command == "send":
                if not args:
                    raise ValueError("Missing arguments for send command")
                can_id = args.get('id', 0x123)
                data = args.get('data', bytes.fromhex("DEADBEEF"))
                self.send_can_message(device, can_id, data)
                return f"Sent CAN message - ID: {hex(can_id)}, Data: {data.hex()}"
            
            else:
                logger.error(f"Unknown command: {command}")
                raise ValueError(f"Unknown command: {command}")
                
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            raise

    def _reset_impl(self, device: SocketCANDevice) -> bool:
        """重置CAN接口"""
        try:
            if self.current_interface:
                import subprocess
                logger.info(f"Resetting interface {self.current_interface}")
                subprocess.run(['sudo', 'ip', 'link', 'set', self.current_interface, 'down'])
                subprocess.run(['sudo', 'ip', 'link', 'set', self.current_interface, 'up'])
                logger.info("SocketCAN device reset successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reset SocketCAN device: {e}")
            raise

    def _close_impl(self, device: SocketCANDevice) -> bool:
        """关闭CAN接口"""
        try:
            logger.info(f"Closing SocketCAN device on {self.current_interface}")
            self.stop_streaming(device)
            if self.current_interface:
                import subprocess
                subprocess.run(['sudo', 'ip', 'link', 'set', self.current_interface, 'down'])
            self.bus = None
            self.current_interface = None
            logger.info("SocketCAN device closed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to close SocketCAN device: {e}")
            raise

    def _setup_acquisition(self, device: Device):
        """设置CAN数据采集"""
        logger.info("Setting up CAN acquisition")
        if not self.bus:
            self.setup_bus()

    def _cleanup_acquisition(self, device: Device):
        """清理CAN数据采集"""
        logger.info("Cleaning up CAN acquisition")
        if self.bus:
            self.shutdown_bus()
            self.bus = None

    def _acquisition_loop(self):
        """CAN数据采集循环"""
        logger.info("Starting CAN acquisition loop")
        while self.is_acquiring.is_set():
            try:
                # 从CAN设备读取数据
                message = self.bus.recv(timeout=0.1)
                if not self.is_acquiring.is_set():
                    break
                if message:
                    # 发送设备数据到客户端
                    stream_data = StreamData(
                        stream_type=StreamType.CAN,
                        channel=self.device.device_id,
                        timestamp=time.time(),
                        source=StreamSource.SERVER,
                        action=StreamAction.DATA,
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

                # 处理来自客户端的数据
                client_data = self.stream_manager.get_client_data()
                if client_data and client_data.stream_type == StreamType.CAN:
                    try:
                        can_data = client_data.data
                        can_id = int(can_data['id'], 16) if isinstance(can_data['id'], str) else can_data['id']
                        data = bytes.fromhex(can_data['data']) if isinstance(can_data['data'], str) else can_data['data']
                        
                        message = can.Message(
                            arbitration_id=can_id,
                            data=data,
                            is_extended_id=can_data.get('is_extended_id', False)
                        )
                        self.bus.send(message)
                        logger.info(f"Sent client CAN message - ID: {hex(message.arbitration_id)}, "
                                  f"Data: {message.data.hex()}")
                    except Exception as e:
                        logger.error(f"Failed to process client CAN data: {e}")

            except Exception as e:
                logger.error(f"Error in CAN acquisition loop: {str(e)}")
                time.sleep(0.1)
        logger.info("CAN acquisition loop stopped")

    def setup_bus(self):
        """设置CAN总线"""
        logger.info(f"Setting up CAN bus on interface {self.current_interface}")
        self.bus = can.interface.Bus(channel=self.current_interface, 
                                   bustype='socketcan')
        logger.debug("CAN bus setup complete")

    def shutdown_bus(self):
        """关闭CAN总线"""
        if self.bus:
            try:
                logger.info("Shutting down CAN bus")
                self.bus.shutdown()
                logger.debug("CAN bus shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")

    def send_can_message(self, device: Device, can_id: int, data: bytes):
        """发送CAN消息"""
        if not self.bus:
            logger.error("Cannot send message: SocketCAN device not connected")
            raise RuntimeError("Cannot send message: SocketCAN device not connected")

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