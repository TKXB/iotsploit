import usb.core
import usb.util
from sat_toolkit.tools.xlogger import xlog
from sat_toolkit.models.Device_Model import Device, DeviceType, USBDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
import time
from pyftdi.ftdi import Ftdi
from pyftdi.serialext import serial_for_url
from sat_toolkit.core.stream_manager import StreamData, StreamType, StreamSource, StreamAction
import pyudev
from typing import List, Optional, Dict

logger = xlog.get_logger(__name__)

# Define the vendor and product IDs for FT2232 devices
FT2232_VENDOR_ID = 0x0403
FT2232_PRODUCT_ID = 0x6010

class FT2232Driver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.uart_channels = {
            'A': None,  # Channel A
            'B': None   # Channel B
        }
        self.mode = 'uart'
        self.connected = False
        self.device = None
        self.usb_dev = None
        self.supported_commands = {
            "start": "Start monitoring/receiving UART data (format: start <channel>)",
            "stop": "Stop monitoring/receiving UART data (format: stop <channel>)",
            "send": "Send data over UART (format: send <channel> <hex_data>)",
            "status": "Display current interface status"
        }

    def _detach_kernel_driver(self, usb_dev):
        """Helper function to detach kernel driver from both interfaces"""
        try:
            for interface in [0, 1]:  # FT2232 has two interfaces
                if usb_dev.is_kernel_driver_active(interface):
                    logger.debug(f"Detaching kernel driver from interface {interface}")
                    usb_dev.detach_kernel_driver(interface)
        except Exception as e:
            logger.warning(f"Error detaching kernel driver: {e}")

    def _attach_kernel_driver(self, usb_dev):
        """Helper function to re-attach kernel driver to both interfaces"""
        try:
            for interface in [0, 1]:  # FT2232 has two interfaces
                if not usb_dev.is_kernel_driver_active(interface):
                    logger.debug(f"Re-attaching kernel driver to interface {interface}")
                    usb_dev.attach_kernel_driver(interface)
        except Exception as e:
            logger.warning(f"Error re-attaching kernel driver: {e}")

    def _scan_impl(self) -> List[Device]:
        """Scan for available FT2232 devices"""
        devices = usb.core.find(find_all=True, idVendor=FT2232_VENDOR_ID, idProduct=FT2232_PRODUCT_ID)
        
        if devices is None:
            logger.info("No FT2232 devices found.")
            return []

        context = pyudev.Context()
        found_devices = []

        for usb_dev in devices:
            try:
                serial_number = usb.util.get_string(usb_dev, usb_dev.iSerialNumber)
                logger.info(f"Found FT2232 device with serial number: {serial_number}")
                
                # Find corresponding ttyUSB devices
                tty_devices = []
                for device in context.list_devices(subsystem='tty', ID_VENDOR_ID=f'{FT2232_VENDOR_ID:04x}'):
                    if device.get('ID_SERIAL_SHORT') == serial_number:
                        tty_devices.append(device.get('DEVNAME'))
                
                tty_devices.sort()
                
                device = USBDevice(
                    device_id=f"ft2232_{serial_number}",
                    name="FT2232",
                    device_type=DeviceType.USB,
                    attributes={
                        'serial_number': serial_number,
                        'vendor_id': FT2232_VENDOR_ID,
                        'product_id': FT2232_PRODUCT_ID,
                        'bus': str(usb_dev.bus),
                        'address': str(usb_dev.address),
                        'port_number': str(usb_dev.port_number) if hasattr(usb_dev, 'port_number') else None,
                        'manufacturer': usb.util.get_string(usb_dev, usb_dev.iManufacturer) if hasattr(usb_dev, 'iManufacturer') else None,
                        'product': usb.util.get_string(usb_dev, usb_dev.iProduct) if hasattr(usb_dev, 'iProduct') else None,
                        'tty_devices': tty_devices,
                        'channel_A': tty_devices[0] if len(tty_devices) > 0 else None,
                        'channel_B': tty_devices[1] if len(tty_devices) > 1 else None
                    }
                )
                
                found_devices.append(device)
                
            except Exception as e:
                logger.error(f"Could not access device: {e}")
                continue

        return found_devices

    def _initialize_impl(self, device: USBDevice) -> bool:
        if device.device_type != DeviceType.USB:
            raise ValueError("This plugin only supports USB devices")
        
        try:
            logger.info(f"Initializing FT2232 device: {device.name}")
            serial_number = device.attributes["serial_number"]
            
            # Find USB device
            self.usb_dev = usb.core.find(idVendor=FT2232_VENDOR_ID, 
                                       idProduct=FT2232_PRODUCT_ID,
                                       serial_number=serial_number)
            if not self.usb_dev:
                raise Exception("USB device not found")

            # Reset and initialize device
            self.usb_dev.reset()
            time.sleep(1)
            self._detach_kernel_driver(self.usb_dev)
            time.sleep(0.5)
            
            # Initialize UART channels
            for channel, index in [('A', 1), ('B', 2)]:
                device_url = f'ftdi://ftdi:2232h:{serial_number}/{index}'
                uart = serial_for_url(
                    device_url,
                    baudrate=115200,
                    bytesize=8,
                    parity='N',
                    stopbits=1
                )
                
                if not uart:
                    raise Exception(f"Failed to create UART interface for channel {channel}")
                
                self.uart_channels[channel] = uart
                
            self.device = device
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize device: {e}")
            self.uart_channels = {'A': None, 'B': None}
            self.device = None
            self.usb_dev = None
            raise

    def _connect_impl(self, device: USBDevice) -> bool:
        try:
            self.connected = all(uart is not None for uart in self.uart_channels.values())
            return self.connected
        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            return False

    def _command_impl(self, device: USBDevice, command: str, args: Optional[Dict] = None) -> Optional[str]:
        try:
            cmd_parts = command.lower().split() if isinstance(command, str) else []
            if not cmd_parts:
                raise ValueError("Empty command received")

            cmd = cmd_parts[0]

            if cmd == "start":
                if len(cmd_parts) < 2:
                    self.start_streaming(device)
                else:
                    channel = cmd_parts[1].upper()
                    if channel not in ['A', 'B']:
                        raise ValueError("Invalid channel. Must be 'A' or 'B'")
                    self.start_streaming(device)

            elif cmd == "stop":
                if len(cmd_parts) < 2:
                    self.stop_streaming(device)
                else:
                    channel = cmd_parts[1].upper()
                    if channel not in ['A', 'B']:
                        raise ValueError("Invalid channel. Must be 'A' or 'B'")
                    self.stop_streaming(device)

            elif cmd == "send":
                if len(cmd_parts) < 3:
                    raise ValueError("Send command requires channel and hex data arguments")
                channel = cmd_parts[1].upper()
                if channel not in ['A', 'B']:
                    raise ValueError("Invalid channel. Must be 'A' or 'B'")
                data = bytes.fromhex(cmd_parts[2])
                self.send_uart_data(device, channel, data)

            elif cmd == "status":
                status = {
                    "mode": self.mode,
                    "channel_A": {
                        "interface_connected": bool(self.uart_channels['A']),
                        "is_acquiring": self.is_acquiring.is_set()
                    },
                    "channel_B": {
                        "interface_connected": bool(self.uart_channels['B']),
                        "is_acquiring": self.is_acquiring.is_set()
                    }
                }
                return str(status)
            else:
                raise ValueError(f"Unknown command: {cmd}")

        except Exception as e:
            logger.error(f"Failed to execute command {command}: {e}")
            raise

    def _reset_impl(self, device: USBDevice) -> bool:
        try:
            logger.info(f"Resetting FT2232 device: {device.name}")
            for channel in self.uart_channels:
                if self.uart_channels[channel]:
                    self.uart_channels[channel].close()
            return True
        except Exception as e:
            logger.error(f"Cannot reset FT2232 device {device.name}: {e}")
            return False

    def _close_impl(self, device: USBDevice) -> bool:
        try:
            for channel in ['A', 'B']:
                if self.uart_channels[channel]:
                    if hasattr(self.uart_channels[channel], '_ftdi'):
                        self.uart_channels[channel]._ftdi.close()
                    self.uart_channels[channel].close()

            self.uart_channels = {'A': None, 'B': None}
            self.connected = False
            
            if self.usb_dev:
                for interface in [0, 1]:
                    usb.util.release_interface(self.usb_dev, interface)
                self.usb_dev.reset()
                time.sleep(1)
                self._attach_kernel_driver(self.usb_dev)
                usb.util.dispose_resources(self.usb_dev)
            
            self.usb_dev = None
            self.device = None
            
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Failed to close FT2232 device {device.name}: {e}")
            self.connected = False
            return False

    def _setup_acquisition(self, device: Device):
        """Setup acquisition for UART channels"""
        logger.info("Setting up UART acquisition")
        self.device = device

    def _cleanup_acquisition(self, device: Device):
        """Cleanup acquisition for UART channels"""
        logger.info("Cleaning up UART acquisition")
        for channel in ['A', 'B']:
            if self.uart_channels[channel]:
                try:
                    if hasattr(self.uart_channels[channel], '_ftdi'):
                        self.uart_channels[channel]._ftdi.close()
                    self.uart_channels[channel].close()
                except Exception as e:
                    logger.warning(f"Error closing channel {channel}: {e}")
                self.uart_channels[channel] = None

    def _acquisition_loop(self):
        """Main acquisition loop for reading from both UART channels"""
        logger.info("Starting UART acquisition loop")
        
        while self.is_acquiring.is_set():
            try:
                # Read from UART channels
                for channel in ['A', 'B']:
                    uart = self.uart_channels[channel]
                    if uart and self.device:
                        try:
                            data = uart.read(16)
                            if data:
                                stream_data = StreamData(
                                    stream_type=StreamType.UART,
                                    channel=self.device.device_id,  # Use device_id only
                                    timestamp=time.time(),
                                    source=StreamSource.SERVER,
                                    action=StreamAction.DATA,
                                    data={
                                        'data': data.hex(),
                                        'length': len(data),
                                        'channel': channel
                                    },
                                    metadata={
                                        'uart_channel': channel,
                                        'baudrate': uart.baudrate
                                    }
                                )
                                self.stream_wrapper.broadcast_data(stream_data)
                                logger.debug(f"Received UART data on channel {channel}: {data.hex()}")
                        except Exception as e:
                            logger.error(f"Error reading UART channel {channel}: {str(e)}")
                            continue

                # Handle data from WebSocket clients
                client_data = self.stream_manager.get_client_data()
                if client_data and client_data.stream_type == StreamType.UART:
                    try:
                        uart_data = client_data.data
                        channel = uart_data.get('channel', 'A')  # Default to channel A if not specified
                        data = bytes.fromhex(uart_data['data']) if isinstance(uart_data['data'], str) else uart_data['data']
                        
                        self.send_uart_data(self.device, channel, data)
                        logger.debug(f"Processed client UART data for channel {channel}: {data.hex()}")
                    except Exception as e:
                        logger.error(f"Failed to process client UART data: {e}")
                
                time.sleep(0.01)  # Small delay to prevent CPU hogging
                
            except Exception as e:
                logger.error(f"Error in acquisition loop: {str(e)}")
                time.sleep(0.1)

    def send_uart_data(self, device: USBDevice, channel: str, data: bytes):
        """Send UART data on a specific channel"""
        if channel not in self.uart_channels:
            raise ValueError(f"Invalid channel: {channel}. Must be 'A' or 'B'")
            
        uart = self.uart_channels[channel]
        if not uart:
            raise Exception("UART channel not initialized")

        try:
            bytes_written = uart.write(data)
            stream_data = StreamData(
                stream_type=StreamType.UART,
                channel=device.device_id,  # Use device_id only
                timestamp=time.time(),
                source=StreamSource.SERVER,
                action=StreamAction.SEND,
                data={
                    'result': 'success',
                    'bytes_written': bytes_written,
                    'channel': channel
                },
                metadata={
                    'uart_channel': channel,
                    'baudrate': uart.baudrate
                }
            )
            self.stream_wrapper.broadcast_data(stream_data)
            logger.info(f"Successfully sent {bytes_written} bytes on UART channel {channel}")
        except Exception as e:
            error_msg = str(e)
            stream_data = StreamData(
                stream_type=StreamType.UART,
                channel=device.device_id,
                timestamp=time.time(),
                source=StreamSource.SERVER,
                action=StreamAction.SEND,
                data={
                    'result': 'error',
                    'error': error_msg,
                    'channel': channel
                },
                metadata={
                    'uart_channel': channel,
                    'baudrate': uart.baudrate if uart else None
                }
            )
            self.stream_wrapper.broadcast_data(stream_data)
            logger.error(f"Failed to send UART data on channel {channel}: {error_msg}")
            raise
