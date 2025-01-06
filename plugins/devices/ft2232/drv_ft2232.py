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

    def initialize(self, device: USBDevice):
        if self.connected and self.device == device:
            logger.info("Device is already initialized and connected.")
            return True

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

            # Reset the device first
            try:
                self.usb_dev.reset()
                time.sleep(1)  # Wait for reset
            except Exception as e:
                logger.warning(f"Device reset failed: {e}")

            # Detach kernel driver using the helper function
            self._detach_kernel_driver(self.usb_dev)
            time.sleep(0.5)  # Wait after detaching

            # Set configuration
            try:
                self.usb_dev.set_configuration()
                time.sleep(0.5)  # Wait for configuration
            except Exception as e:
                logger.error(f"Error setting configuration: {e}")
                raise

            # Verify kernel driver is detached
            for interface in [0, 1]:
                if self.usb_dev.is_kernel_driver_active(interface):
                    raise Exception(f"Kernel driver still active on interface {interface}")

            # Initialize UART channels
            for channel, index in [('A', 1), ('B', 2)]:
                try:
                    device_url = f'ftdi://ftdi:2232h:{serial_number}/{index}'
                    logger.info(f"Creating UART interface for channel {channel}")
                    
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
                    logger.info(f"Successfully initialized channel {channel}")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize channel {channel}: {e}")
                    raise

            # Verify TTY devices are gone (kernel driver successfully detached)
            if any(Path(f"/dev/ttyUSB{i}").exists() for i in [1, 2]):
                logger.warning("TTY devices still exist after initialization")
            
            self.connected = True
            self.device = device
            logger.info("Device initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize device: {e}")
            self.connected = False
            self.uart_channels = {'A': None, 'B': None}
            self.device = None
            self.usb_dev = None
            raise

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
            if not self.initialize(device):
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
                self.reset(device)
            except Exception as reset_error:
                logger.error(f"Failed to reset device after send error: {reset_error}")
            raise

    def command(self, device: USBDevice, command: str):
        try:
            cmd_parts = command.lower().split()
            if len(cmd_parts) < 1:
                logger.error("Empty command received")
                return

            cmd = cmd_parts[0]

            if not self.connected and cmd != "status":
                logger.info("Device not connected, attempting to initialize...")
                if not self.initialize(device):
                    logger.error("Failed to initialize device")
                    return

            if cmd == "start":
                # Ensure kernel driver is detached before starting
                if self.usb_dev:
                    self._detach_kernel_driver(self.usb_dev)
                    # Verify TTY devices are gone
                    timeout = 5  # 5 seconds timeout
                    start_time = time.time()
                    while time.time() - start_time < timeout:
                        if not any(Path(f"/dev/ttyUSB{i}").exists() for i in [1, 2]):
                            logger.info("TTY devices successfully removed")
                            break
                        time.sleep(0.5)
                    else:
                        logger.warning("TTY devices still present after timeout")

                if len(cmd_parts) < 2:
                    # If no channel specified, start both channels
                    logger.info("No channel specified, starting both channels")
                    for channel in ['A', 'B']:
                        self.start_monitoring(device, channel)
                else:
                    channel = cmd_parts[1].upper()
                    self.start_monitoring(device, channel)

            elif cmd == "stop":
                if len(cmd_parts) < 2:
                    # If no channel specified, stop both channels
                    logger.info("No channel specified, stopping both channels")
                    for channel in ['A', 'B']:
                        self.stop_monitoring(device, channel)
                    
                    # Add delay after stopping channels
                    time.sleep(1)
                    
                    # Release USB interfaces before reattaching
                    if self.usb_dev:
                        for interface in [0, 1]:
                            try:
                                usb.util.release_interface(self.usb_dev, interface)
                            except Exception as e:
                                logger.warning(f"Error releasing interface {interface}: {e}")
                        
                        # Add delay after releasing interfaces
                        time.sleep(0.5)
                        
                        # Re-attach kernel driver after stopping all channels
                        self._attach_kernel_driver(self.usb_dev)
                        
                        # Wait for TTY devices to appear
                        timeout = 5  # 5 seconds timeout
                        start_time = time.time()
                        while time.time() - start_time < timeout:
                            if all(Path(f"/dev/ttyUSB{i}").exists() for i in [1, 2]):
                                logger.info("TTY devices successfully restored")
                                break
                            time.sleep(0.5)
                        else:
                            logger.warning("TTY devices did not reappear after timeout")
                else:
                    channel = cmd_parts[1].upper()
                    self.stop_monitoring(device, channel)

            elif cmd == "send":
                if len(cmd_parts) < 3:
                    logger.error("Send command requires channel and hex data arguments")
                    return
                channel = cmd_parts[1].upper()
                try:
                    data = bytes.fromhex(cmd_parts[2])
                    self.send_uart_data(device, channel, data)
                except ValueError:
                    logger.error("Invalid hex data format")

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
                logger.info(f"Device status: {status}")

            else:
                logger.error(f"Unknown command: {cmd}. Valid commands are: {', '.join(self.supported_commands.keys())}")

        except Exception as e:
            logger.error(f"Failed to execute command {command}: {e}")
            raise

    def reset(self, device: USBDevice):
        try:
            logger.info(f"Resetting FT2232 device: {device.name}")
            for channel in self.uart_channels:
                if self.uart_channels[channel]:
                    self.uart_channels[channel].close()
                    
            # Reinitialize both channels
            self.initialize(device)
            logger.info(f"Reset FT2232 device: {device.name}")
            return True
        except Exception as e:
            logger.error(f"Cannot reset FT2232 device {device.name}: {e}")
            return False

    def close(self, device: USBDevice):
        try:
            # Stop all receivers first
            for channel in ['A', 'B']:
                self.stop_receiver(channel)
            
            # Close each channel
            for channel, uart in self.uart_channels.items():
                if uart:
                    try:
                        if hasattr(uart, '_ftdi'):
                            # Close FTDI connection properly
                            uart._ftdi.close()
                        uart.close()
                    except Exception as e:
                        logger.warning(f"Error closing channel {channel}: {e}")

            self.uart_channels = {'A': None, 'B': None}
            self.connected = False
            
            # Reset and cleanup USB device
            if self.usb_dev:
                try:
                    # Release claimed interfaces
                    for interface in [0, 1]:
                        try:
                            usb.util.release_interface(self.usb_dev, interface)
                        except Exception as e:
                            logger.warning(f"Error releasing interface {interface}: {e}")
                    
                    # Reset the device
                    self.usb_dev.reset()
                    time.sleep(1)  # Wait for reset to complete
                    
                    # Re-attach kernel driver
                    for interface in [0, 1]:
                        try:
                            if not self.usb_dev.is_kernel_driver_active(interface):
                                logger.info(f"Re-attaching kernel driver to interface {interface}")
                                self.usb_dev.attach_kernel_driver(interface)
                                time.sleep(0.5)  # Wait between attaching
                        except Exception as e:
                            logger.warning(f"Error re-attaching kernel driver to interface {interface}: {e}")
                    
                    # Dispose of USB resources
                    usb.util.dispose_resources(self.usb_dev)
                    
                except Exception as e:
                    logger.warning(f"Error during USB device cleanup: {e}")
            
            self.usb_dev = None
            self.device = None
            
            # Add a longer delay to ensure device re-enumeration
            time.sleep(2)
            
            # Verify TTY devices are back
            timeout = 5  # 5 seconds timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                if all(Path(f"/dev/ttyUSB{i}").exists() for i in [1, 2]):
                    logger.info("TTY devices successfully restored")
                    break
                time.sleep(0.5)
            else:
                logger.warning("TTY devices did not reappear after timeout")
            
            logger.info(f"FT2232 device {device.name} closed successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to close FT2232 device {device.name}: {e}")
            self.connected = False
            return False

    def connect(self, device: USBDevice):
        """Connect to the device after initialization"""
        try:
            if not any(self.uart_channels.values()):
                self.initialize(device)
            
            self.connected = all(uart is not None for uart in self.uart_channels.values())
            if self.connected:
                logger.info(f"Connected to FT2232 device: {device.name}")
            else:
                logger.error("Not all channels were initialized properly")
            
            return self.connected
            
        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            self.connected = False
            return False

    def scan(self):
        """Scan for available FT2232 devices"""
        devices = usb.core.find(find_all=True, idVendor=FT2232_VENDOR_ID, idProduct=FT2232_PRODUCT_ID)
        
        if devices is None:
            logger.info("No FT2232 devices found.")
            return []

        # Initialize pyudev context
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
                
                tty_devices.sort()  # Sort to ensure consistent ordering
                
                # Create device object with additional tty information
                device = USBDevice(
                    device_id=f"ft2232_{serial_number}",
                    name="FT2232",
                    device_type=DeviceType.USB,  # Add device_type for compatibility
                    attributes={
                        'serial_number': serial_number,
                        'vendor_id': FT2232_VENDOR_ID,
                        'product_id': FT2232_PRODUCT_ID,
                        'bus': str(usb_dev.bus),
                        'address': str(usb_dev.address),
                        'port_number': str(usb_dev.port_number) if hasattr(usb_dev, 'port_number') else None,
                        'manufacturer': usb.util.get_string(usb_dev, usb_dev.iManufacturer) if hasattr(usb_dev, 'iManufacturer') else None,
                        'product': usb.util.get_string(usb_dev, usb_dev.iProduct) if hasattr(usb_dev, 'iProduct') else None,
                        'tty_devices': tty_devices,  # Add the tty device paths
                        'channel_A': tty_devices[0] if len(tty_devices) > 0 else None,  # First TTY device is channel A
                        'channel_B': tty_devices[1] if len(tty_devices) > 1 else None   # Second TTY device is channel B
                    }
                )
                
                logger.info(f"Found TTY devices for {serial_number}: {tty_devices}")
                found_devices.append(device)
                
            except usb.core.USBError as e:
                logger.error(f"Could not access device: {e}")
                continue
            except Exception as e:
                logger.error(f"Error creating device object: {e}")
                continue

        return found_devices

    def __del__(self):
        """Cleanup method called when the driver is destroyed"""
        if self.device:
            try:
                self.close(self.device)
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


# Example usage
if __name__ == "__main__":
    from sat_toolkit.models.Device_Model import USBDevice
    
    ability = FT2232Driver()
    
    found_devices = ability.scan()
    if found_devices:
        test_device = found_devices[0]  # Use the first found device
        test_device.attributes['mode'] = 'uart'  # Set the mode
        print(f"FT2232 Device Found: {test_device}")
        ability.initialize(test_device)
        if ability.connect(test_device):
            print("Device connected successfully.")
            ability.command(test_device, "test_command")
            ability.reset(test_device)
            if ability.close(test_device):
                print("Device closed successfully.")
            else:
                print("Failed to close device.")
        else:
            print("Failed to connect to device.")
    else:
        print("No FT2232 devices found.")
