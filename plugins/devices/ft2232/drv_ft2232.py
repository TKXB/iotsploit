import usb.core
import usb.util
from sat_toolkit.tools.xlogger import xlog
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, USBDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
import uuid
import threading
import time
from pyftdi.ftdi import Ftdi
from pyftdi.serialext import serial_for_url
from sat_toolkit.core.stream_manager import StreamManager, StreamData, StreamType, StreamSource, StreamAction, StreamWrapper
import asyncio
import pyudev
from pathlib import Path
from typing import List, Optional

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
        self._device_counter = 0
        self.running = {
            'A': threading.Event(),
            'B': threading.Event()
        }
        self.receiver_threads = {
            'A': None,
            'B': None
        }
        self.connected = False
        self.stream_manager = StreamManager()
        self.stream_wrapper = StreamWrapper(self.stream_manager)
        self.device = None
        self.usb_dev = None  # Store USB device reference
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
            if not any(self.uart_channels.values()):
                self._initialize_impl(device)
            
            self.connected = all(uart is not None for uart in self.uart_channels.values())
            return self.connected
            
        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            return False

    def _command_impl(self, device: USBDevice, command: str) -> Optional[str]:
        try:
            cmd_parts = command.lower().split()
            if len(cmd_parts) < 1:
                raise ValueError("Empty command received")

            cmd = cmd_parts[0]

            if cmd == "start":
                if len(cmd_parts) < 2:
                    for channel in ['A', 'B']:
                        self.start_monitoring(device, channel)
                else:
                    channel = cmd_parts[1].upper()
                    self.start_monitoring(device, channel)

            elif cmd == "stop":
                if len(cmd_parts) < 2:
                    for channel in ['A', 'B']:
                        self.stop_monitoring(device, channel)
                else:
                    channel = cmd_parts[1].upper()
                    self.stop_monitoring(device, channel)

            elif cmd == "send":
                if len(cmd_parts) < 3:
                    raise ValueError("Send command requires channel and hex data arguments")
                channel = cmd_parts[1].upper()
                data = bytes.fromhex(cmd_parts[2])
                self.send_uart_data(device, channel, data)

            elif cmd == "status":
                status = {
                    "mode": self.mode,
                    "channel_A": {
                        "running": self.running['A'].is_set(),
                        "receiver_active": bool(self.receiver_threads['A'] and self.receiver_threads['A'].is_alive()),
                        "interface_connected": bool(self.uart_channels['A'])
                    },
                    "channel_B": {
                        "running": self.running['B'].is_set(),
                        "receiver_active": bool(self.receiver_threads['B'] and self.receiver_threads['B'].is_alive()),
                        "interface_connected": bool(self.uart_channels['B'])
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
                    
            self._initialize_impl(device)
            return True
        except Exception as e:
            logger.error(f"Cannot reset FT2232 device {device.name}: {e}")
            return False

    def _close_impl(self, device: USBDevice) -> bool:
        try:
            for channel in ['A', 'B']:
                self.stop_receiver(channel)
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

    def receiver_thread_fn(self, channel):
        """Thread function to continuously read UART data for a specific channel"""
        uart = self.uart_channels[channel]
        channel_id = f"{self.device.device_id}_{channel}"
        
        while self.running[channel].is_set():
            try:
                logger.debug(f"UART: {uart}, Device: {self.device}")
                if uart and self.device:
                    data = uart.read(16)
                    if data:
                        stream_data = StreamData(
                            stream_type=StreamType.UART,
                            channel=channel_id,
                            timestamp=time.time(),
                            source=StreamSource.SERVER,
                            action=StreamAction.DATA,
                            data={
                                'data': data.hex(),
                                'length': len(data),
                                'channel': channel
                            },
                            metadata={
                                'interface': channel_id,
                                'baudrate': uart.baudrate,
                                'channel': channel
                            }
                        )
                        self.stream_wrapper.broadcast_data(stream_data)
                        logger.info(f"Received UART data on channel {channel}: {data.hex()}")
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error reading UART data on channel {channel}: {str(e)}")
                time.sleep(0.1)

    def start_monitoring(self, device, channel):
        """Start UART monitoring for a specific channel"""
        if channel not in self.uart_channels:
            raise ValueError(f"Invalid channel: {channel}. Must be 'A' or 'B'")
            
        self.stop_receiver(channel)
        logger.info(f"Starting UART monitoring for channel {channel}")
        channel_id = f"{device.device_id}_{channel}"
        self.stream_wrapper.register_stream(channel_id)
        self.start_receiver(channel)

    def stop_monitoring(self, device, channel):
        """Stop UART monitoring for a specific channel"""
        if channel not in self.uart_channels:
            raise ValueError(f"Invalid channel: {channel}. Must be 'A' or 'B'")
            
        channel_id = f"{device.device_id}_{channel}"
        self.stream_wrapper.unregister_stream(channel_id)
        self.stream_wrapper.stop_broadcast(channel_id)
        self.stop_receiver(channel)

    def start_receiver(self, channel):
        """Start receiver thread for a specific channel"""
        if not self.running[channel].is_set() and not (self.receiver_threads[channel] and self.receiver_threads[channel].is_alive()):
            self.running[channel].set()
            self.receiver_threads[channel] = threading.Thread(
                target=self.receiver_thread_fn,
                args=(channel,),
                name=f'FT2232_RECEIVER_{channel}'
            )
            self.receiver_threads[channel].daemon = True
            self.receiver_threads[channel].start()
            logger.info(f"Started UART monitoring for channel {channel}")

    def stop_receiver(self, channel):
        """Stop receiver thread for a specific channel"""
        self.running[channel].clear()
        if self.receiver_threads[channel] and self.receiver_threads[channel].is_alive():
            self.receiver_threads[channel].join(timeout=1.0)
            self.receiver_threads[channel] = None
        
        # Close the UART channel when stopping
        if self.uart_channels[channel]:
            try:
                if hasattr(self.uart_channels[channel], '_ftdi'):
                    self.uart_channels[channel]._ftdi.close()
                self.uart_channels[channel].close()
                self.uart_channels[channel] = None
            except Exception as e:
                logger.warning(f"Error closing channel {channel}: {e}")
        
        logger.info(f"Stopped UART monitoring for channel {channel}")

    def send_uart_data(self, device: USBDevice, channel: str, data: bytes):
        """Send UART data on a specific channel"""
        if channel not in self.uart_channels:
            raise ValueError(f"Invalid channel: {channel}. Must be 'A' or 'B'")
            
        uart = self.uart_channels[channel]
        if not uart:
            # Try to reinitialize if the channel is not connected
            if not self._initialize_impl(device):
                logger.error("Cannot send data: UART channel initialization failed")
                raise Exception("Failed to initialize UART channel")

        try:
            # Ensure kernel driver is detached before sending data
            if self.usb_dev:
                interface = 0 if channel == 'A' else 1
                if self.usb_dev.is_kernel_driver_active(interface):
                    logger.debug(f"Detaching kernel driver from interface {interface}")
                    self.usb_dev.detach_kernel_driver(interface)

            uart.write(data)
            channel_id = f"{device.device_id}_{channel}"
            stream_data = StreamData(
                stream_type=StreamType.UART,
                channel=channel_id,
                timestamp=time.time(),
                source=StreamSource.SERVER,
                action=StreamAction.SEND,
                data={
                    'data': data.hex(),
                    'length': len(data),
                    'channel': channel
                },
                metadata={
                    'interface': channel_id,
                    'baudrate': uart.baudrate,
                    'channel': channel
                }
            )
            self.stream_wrapper.broadcast_data(stream_data)
            logger.info(f"Sent UART data on channel {channel}: {data.hex()}")
        except Exception as e:
            logger.error(f"Failed to send UART data on channel {channel}: {e}")
            # Try to recover by reinitializing the device
            try:
                self._reset_impl(device)
            except Exception as reset_error:
                logger.error(f"Failed to reset device after send error: {reset_error}")
            raise

    def __del__(self):
        """Cleanup method called when the driver is destroyed"""
        if self.device:
            try:
                self._close_impl(self.device)
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


# Example usage
if __name__ == "__main__":
    from sat_toolkit.models.Device_Model import USBDevice
    
    ability = FT2232Driver()
    
    found_devices = ability._scan_impl()
    if found_devices:
        test_device = found_devices[0]  # Use the first found device
        test_device.attributes['mode'] = 'uart'  # Set the mode
        print(f"FT2232 Device Found: {test_device}")
        ability._initialize_impl(test_device)
        if ability._connect_impl(test_device):
            print("Device connected successfully.")
            ability._command_impl(test_device, "test_command")
            ability._reset_impl(test_device)
            if ability._close_impl(test_device):
                print("Device closed successfully.")
            else:
                print("Failed to close device.")
        else:
            print("Failed to connect to device.")
    else:
        print("No FT2232 devices found.")
