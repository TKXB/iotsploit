import pluggy
import pylink
import logging
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType
from sat_toolkit.core.base_plugin import BaseDeviceDriver
logger = logging.getLogger(__name__)

hookimpl = pluggy.HookimplMarker("device_mgr")

class JLinkAbility(BaseDeviceDriver):
    def __init__(self):
        self.jlink = None
        self.connected_emulators = []

    @hookimpl
    def scan(self, device: Device = None):
        try:
            jlink = pylink.JLink()
            self.connected_emulators = jlink.connected_emulators()
            if self.connected_emulators:
                print(f"Found JLink emulator(s): {self.connected_emulators}")
                if device and device.device_type == DeviceType.JTAG:
                    device.attributes['emulator_sn'] = self.connected_emulators[0].SerialNumber
                return True
            else:
                print("No JLink emulators found")
                return False
        except Exception as e:
            print(f"Error scanning for JLink devices: {str(e)}")
            return False

    @hookimpl
    def initialize(self, device: Device = None):
        if not self.connected_emulators:
            if not self.scan(device):
                raise ValueError("No JLink emulators found. Please run scan first.")
        
        if device:
            if device.device_type != DeviceType.JTAG:
                raise ValueError("This plugin only supports JTAG devices")
            self.current_device = device
        else:
            # If no device is provided, create a default one
            self.current_device = Device("Default JTAG Device", DeviceType.JTAG)
        
        emulator_sn = self.current_device.attributes.get('emulator_sn') or self.connected_emulators[0].SerialNumber
        self.jlink = pylink.JLink()
        self.jlink.open(serial_no=emulator_sn)
        
        # Connect to the target device
        target_device = self.current_device.attributes.get('target_device', 'STM32F407VG')
        self.jlink.connect(target_device)
        
        logger.info(f"Initializing JTAG device: {self.current_device.name} connected to {target_device}")


    @hookimpl
    def execute(self, device: Device, target: str):
        if not self.jlink:
            raise ValueError("JLink device not initialized")
        
        if target == "read_memory":
            mem = self.jlink.memory_read32(0x08000000, 10)
            print(f"Memory read from {device.name}: {mem}")
        elif target == "write_memory":
            self.jlink.memory_write32(0x20000000, [0x12345678])
            print(f"Memory written to {device.name}")
        else:
            print(f"Unknown target: {target}")

    @hookimpl
    def send_command(self, device: Device, command: str):
        if not self.jlink:
            raise ValueError("JLink device not initialized")
        
        # Implement custom commands here
        if command == "reset":
            self.jlink.reset()
            print(f"Reset {device.name}")
        else:
            print(f"Unknown command: {command}")

    @hookimpl
    def reset(self, device: Device):
        if self.jlink:
            self.jlink.reset()
            print(f"Reset JTAG device: {device.name}")

    @hookimpl
    def close(self, device: Device):
        if self.jlink:
            self.jlink.close()
            self.jlink = None
        print(f"Closed JTAG device: {device.name}")
