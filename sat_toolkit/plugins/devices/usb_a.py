import pluggy
import logging
import serial
import serial.tools.list_ports
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType

logger = logging.getLogger(__name__)

hookimpl = pluggy.HookimplMarker("device_mgr")

class USBAbility:
    def __init__(self):
        self.serial_connection = None

    @hookimpl
    def scan(self, device: Device):
        if device.device_type not in [DeviceType.USB, DeviceType.Serial]:
            return False

        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.vid == 0x10c4 and port.pid == 0xea60:
                device.attributes['port'] = port.device
                logger.info(f"Found USB/Serial device on port: {port.device}")
                return True
        
        logger.info("No matching USB/Serial device found")
        return False

    @hookimpl
    def initialize(self, device: Device):
        if device.device_type not in [DeviceType.USB, DeviceType.Serial]:
            logger.error(f"Current device type: {device.device_type}")
            raise ValueError("This plugin only supports USB and Serial devices")
        
        if 'port' not in device.attributes:
            # Perform scanning if port is not set
            if not self.scan(device):
                raise ValueError("No compatible USB/Serial device found. Unable to initialize.")
        
        logger.info(f"Initializing USB/Serial device: {device.name} on port {device.attributes['port']}")
        # Add any additional initialization logic here

    @hookimpl
    def execute(self, device: Device, target: str):
        if device.device_type == DeviceType.Serial:
            self._connect_serial(device)
            self._print_uart_log()
        else:
            logger.info(f"Executing USB exploit on {target} using device {device.name}")

    @hookimpl
    def send_command(self, device: Device, command: str):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.write(command.encode())
            logger.info(f"Sent command '{command}' to device {device.name}")
        else:
            logger.error(f"Cannot send command: device {device.name} is not connected")

    def reset(self, device: Device):
        if self.serial_connection:
            self.serial_connection.close()
        self._connect_serial(device)
        logger.info(f"Reset USB/Serial device: {device.name}")

    @hookimpl
    def close(self, device: Device):
        if self.serial_connection:
            self.serial_connection.close()
        logger.info(f"Closed USB/Serial device: {device.name}")
    
    def _connect_serial(self, device: Device):
        if 'port' not in device.attributes:
            raise ValueError("Serial port not specified for the device")
        
        self.serial_connection = serial.Serial(
            port=device.attributes['port'],
            baudrate=115200,
            timeout=1
        )
        logger.info(f"Connected to {device.attributes['port']} at 115200 baud")

    def _print_uart_log(self):
        logger.info("UART Log:")
        try:
            while True:
                if self.serial_connection.in_waiting:
                    line = self.serial_connection.readline().decode('utf-8').strip()
                    logger.info(line)
        except KeyboardInterrupt:
            logger.info("Stopped reading UART log")

def register_plugin(pm):
    usb_ability = USBAbility()
    pm.register(usb_ability)