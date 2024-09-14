import pluggy
import pylink
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device, DeviceType

hookimpl = pluggy.HookimplMarker("device_mgr")

class JLinkAbility:
    def __init__(self):
        self.jlink = None

    @hookimpl
    def initialize(self, device: Device):
        if device.device_type != DeviceType.JTAG:
            raise ValueError("This plugin only supports JTAG devices")
        
        self.jlink = pylink.JLink()
        self.jlink.open()
        
        # Connect to the target device
        target_device = device.attributes.get('target_device', 'STM32F407VG')
        self.jlink.connect(target_device)
        
        print(f"Initializing JTAG device: {device.name} connected to {target_device}")

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