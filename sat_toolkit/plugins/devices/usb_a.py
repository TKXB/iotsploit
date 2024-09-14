import pluggy
import serial
import serial.tools.list_ports
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType

hookimpl = pluggy.HookimplMarker("device_mgr")

class USBAbility:
    @hookimpl
    def initialize(self, device: Device):
        if device.device_type not in [DeviceType.USB, DeviceType.Serial]:
            print(f"Current device type: {device.device_type}") 
            raise ValueError("This plugin only supports USB and Serial devices")
        
        # Find the device using VID:PID
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.vid == 0x10c4 and port.pid == 0xea60:
                device.attributes['port'] = port.device
                break
        else:
            raise ValueError("Device with VID:PID 10c4:ea60 not found")

        print(f"Initializing USB/Serial device: {device.name} on port {device.attributes['port']}")


    @hookimpl
    def execute(self, device: Device, target: str):
        if device.device_type == DeviceType.Serial:
            self._connect_serial(device)
            self._print_uart_log()
        else:
            print(f"Executing USB exploit on {target} using device {device.name}")

    @hookimpl
    def send_command(self, device: Device, command: str):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.write(command.encode())
            print(f"Sent command '{command}' to device {device.name}")
        else:
            print(f"Cannot send command: device {device.name} is not connected")

    def reset(self, device: Device):
        if self.serial_connection:
            self.serial_connection.close()
        self._connect_serial(device)
        print(f"Reset USB/Serial device: {device.name}")

    @hookimpl
    def close(self, device: Device):
        if self.serial_connection:
            self.serial_connection.close()
        print(f"Closed USB/Serial device: {device.name}")
    
    def _connect_serial(self, device: Device):
        if 'port' not in device.attributes:
            raise ValueError("Serial port not specified for the device")
        
        self.serial_connection = serial.Serial(
            port=device.attributes['port'],
            baudrate=115200,
            timeout=1
        )
        print(f"Connected to {device.attributes['port']} at 115200 baud")

    def _print_uart_log(self):
        print("UART Log:")
        try:
            while True:
                if self.serial_connection.in_waiting:
                    line = self.serial_connection.readline().decode('utf-8').strip()
                    print(line)
        except KeyboardInterrupt:
            print("Stopped reading UART log")