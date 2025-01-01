import usb.core
import usb.util
import pluggy
import logging
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType, USBDevice
from sat_toolkit.core.base_plugin import BaseDeviceDriver
import uuid
from plugins.devices.ft2232.protocol import (
    create_ft2232_interface, close_ft2232_interface,
    uart_read, uart_write, spi_exchange, jtag_write_tms, jtag_write_tdi
)
import threading
import time

logger = logging.getLogger(__name__)

hookimpl = pluggy.HookimplMarker("device_mgr")

# Define the vendor and product IDs for FT2232 devices
FT2232_VENDOR_ID = 0x0403
FT2232_PRODUCT_ID = 0x6010

class FT2232Driver(BaseDeviceDriver):
    def __init__(self):
        super().__init__()
        self.ft2232_interface = None
        self.mode = None
        self._device_counter = 0
        self.running = threading.Event()
        self.receiver_thread = None
        self.connected = False
        # Define commands with descriptions
        self.supported_commands = {
            "start": "Start monitoring/receiving UART data",
            "stop": "Stop monitoring/receiving UART data",
            "send": "Send data over UART (format: send <hex_data>)",
            "mode": "Set interface mode (uart/spi/jtag)",
            "status": "Display current interface status and mode"
        }

    def start_receiver(self):
        """Helper method to start the receiver thread if it's not already running"""
        if not self.running.is_set() and not (self.receiver_thread and self.receiver_thread.is_alive()):
            self.running.set()
            self.receiver_thread = threading.Thread(
                target=self.receiver_thread_fn,
                name='FT2232_RECEIVER'
            )
            self.receiver_thread.daemon = True
            self.receiver_thread.start()
            logger.info("Started UART monitoring")

    def stop_receiver(self):
        """Helper method to stop the receiver thread"""
        self.running.clear()
        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=1.0)
            self.receiver_thread = None
        logger.info("Stopped UART monitoring")

    def receiver_thread_fn(self):
        """Thread function to continuously read UART data"""
        while self.running.is_set():
            try:
                if self.mode == 'uart' and self.ft2232_interface:
                    data = uart_read(self.ft2232_interface)
                    if data:
                        logger.info(f"Received UART data: {data.hex()}")
                time.sleep(0.01)  # Small delay to prevent CPU hogging
            except Exception as e:
                logger.error(f"Error reading UART data: {str(e)}")
                time.sleep(0.1)

    @hookimpl
    def scan(self):
        devices = usb.core.find(find_all=True, idVendor=FT2232_VENDOR_ID, idProduct=FT2232_PRODUCT_ID)
        
        if devices is None:
            logger.info("No FT2232 devices found.")
            return []

        found_devices = []
        for usb_dev in devices:
            try:
                serial_number = usb.util.get_string(usb_dev, usb_dev.iSerialNumber)
                logger.info(f"Found FT2232 device with serial number: {serial_number}")
                
                # 创建可序列化的设备对象
                device = USBDevice(
                    device_id=f"ft2232_{serial_number}",
                    name="FT2232",
                    vendor_id=hex(FT2232_VENDOR_ID),
                    product_id=hex(FT2232_PRODUCT_ID),
                    attributes={
                        'serial_number': serial_number,
                        'bus': str(usb_dev.bus),
                        'address': str(usb_dev.address),
                        'port_number': str(usb_dev.port_number) if hasattr(usb_dev, 'port_number') else None,
                        'manufacturer': usb.util.get_string(usb_dev, usb_dev.iManufacturer) if hasattr(usb_dev, 'iManufacturer') else None,
                        'product': usb.util.get_string(usb_dev, usb_dev.iProduct) if hasattr(usb_dev, 'iProduct') else None
                    }
                )
                
                # 使用 dataclasses-json 的序列化方法验证
                device_dict = device.to_dict()  # 验证可以序列化
                found_devices.append(device)
                
            except usb.core.USBError as e:
                logger.error(f"Could not access device: {e}")
                continue
            except Exception as e:
                logger.error(f"Error creating device object: {e}")
                continue

        return found_devices

    @hookimpl
    def initialize(self, device: USBDevice):
        if device.device_type != DeviceType.USB:
            logger.error(f"Current device type: {device.device_type}")
            raise ValueError("This plugin only supports USB devices")
        
        try:
            logger.info(f"Initializing FT2232 device: {device.name}")
            self.mode = device.attributes.get('mode', 'uart')  # Default to UART
            
            # Updated URL format
            serial_number = device.attributes["serial_number"]
            device_url = f'ftdi://ftdi:2232h:{serial_number}/1'
            
            logger.debug(f"Attempting to create interface with URL: {device_url}")
            self.ft2232_interface = create_ft2232_interface(self.mode, device_url)
            
            if not self.ft2232_interface:
                raise Exception("Failed to create FT2232 interface")
                
            # Test the connection
            if self.mode == 'uart':
                self.ft2232_interface.write(b'\x00')  # Send a null byte to test connection
                
            self.connected = True
            logger.info(f"Successfully initialized FT2232 device with serial: {serial_number}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize device: {e}")
            self.connected = False
            self.ft2232_interface = None
            raise

    @hookimpl
    def connect(self, device: USBDevice):
        try:
            if not self.ft2232_interface:
                logger.error("FT2232 interface not initialized. Please initialize first.")
                self.connected = False
                return False

            # Test the connection
            if self.mode == 'uart':
                self.ft2232_interface.write(b'\x00')  # Send a null byte to test connection

            logger.info(f"FT2232 device {device.name} connected successfully in {self.mode} mode.")
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            return False

    @hookimpl
    def execute(self, device: USBDevice, target: str):
        logger.info(f"Executing action on {target} using FT2232 device {device.name}")
        # Implement specific FT2232 execution logic here based on the mode

    @hookimpl
    def command(self, device: USBDevice, command: str):
        try:
            cmd_parts = command.lower().split()
            cmd = cmd_parts[0]
            args = cmd_parts[1:] if len(cmd_parts) > 1 else []

            if not self.ft2232_interface:
                try:
                    logger.info("Device not connected, attempting to initialize...")
                    self.initialize(device)
                    self.connect(device)
                except Exception as e:
                    logger.error(f"Failed to initialize or connect to device: {e}")
                    return

            if cmd == "start":
                if self.mode != 'uart':
                    logger.info("Switching to UART mode for start command")
                    self.mode = 'uart'
                    serial_number = device.attributes["serial_number"]
                    device_url = f'ftdi://:2232h:{serial_number}/1'  # 保持与 initialize 相同的 URL 格式
                    close_ft2232_interface(self.mode, self.ft2232_interface)
                    self.ft2232_interface = create_ft2232_interface(self.mode, device_url)
                self.start_receiver()

            elif cmd == "stop":
                self.stop_receiver()

            elif cmd == "send":
                if self.mode != 'uart':
                    logger.error("Send command only available in UART mode")
                    return
                if not args:
                    logger.error("Send command requires hex data argument")
                    return
                try:
                    data = bytes.fromhex(args[0])
                    uart_write(self.ft2232_interface, data)
                    logger.info(f"Sent UART data: {data.hex()}")
                except ValueError:
                    logger.error("Invalid hex data format")

            elif cmd == "mode":
                if not args:
                    logger.error("Mode command requires argument (uart/spi/jtag)")
                    return
                new_mode = args[0]
                if new_mode in ['uart', 'spi', 'jtag']:
                    # Stop any ongoing operations
                    self.stop_receiver()
                    # Close and recreate interface with new mode
                    close_ft2232_interface(self.mode, self.ft2232_interface)
                    device_url = f'ftdi://ftdi:2232h/{device.attributes["serial_number"]}'
                    self.mode = new_mode
                    self.ft2232_interface = create_ft2232_interface(self.mode, device_url)
                    logger.info(f"Changed mode to: {new_mode}")
                else:
                    logger.error("Invalid mode specified")

            elif cmd == "status":
                status = {
                    "mode": self.mode,
                    "running": self.running.is_set(),
                    "receiver_active": bool(self.receiver_thread and self.receiver_thread.is_alive()),
                    "interface_connected": bool(self.ft2232_interface)
                }
                logger.info(f"Device status: {status}")

            else:
                logger.error(f"Unknown command: {cmd}. Valid commands are: {', '.join(self.supported_commands.keys())}")

        except Exception as e:
            logger.error(f"Failed to execute command {command}: {e}")
            raise

    @hookimpl
    def reset(self, device: USBDevice):
        if self.ft2232_interface:
            close_ft2232_interface(self.mode, self.ft2232_interface)
            device_url = f'ftdi://ftdi:2232h/{device.attributes["serial_number"]}'
            self.ft2232_interface = create_ft2232_interface(self.mode, device_url)
            logger.info(f"Reset FT2232 device: {device.name}")
        else:
            logger.error(f"Cannot reset: FT2232 device {device.name} is not connected")

    @hookimpl
    def close(self, device: USBDevice):
        if not self.ft2232_interface:
            logger.error("FT2232 interface not found. Nothing to close.")
            self.connected = False
            return False

        try:
            close_ft2232_interface(self.mode, self.ft2232_interface)
            self.ft2232_interface = None
            self.connected = False
            logger.info(f"FT2232 device {device.name} closed successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to close FT2232 device {device.name}: {e}")
            self.connected = False
            return False


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
