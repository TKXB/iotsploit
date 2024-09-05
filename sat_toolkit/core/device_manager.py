import pluggy
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device

class DeviceManager:
    def __init__(self):
        print("Initializing DeviceManager")
        self.pm = pluggy.PluginManager("device_mgr")
        self.pm.add_hookspecs(DevicePluginSpec)
        print("DeviceManager initialized")

    def register_plugin(self, plugin):
        self.pm.register(plugin)

    def initialize_device(self, device: Device):
        print("Initializing device from DeviceManager")
        self.pm.hook.initialize(device=device)

    def execute_on_target(self, device: Device, target: str):
        self.pm.hook.execute(device=device, target=target)

    def send_command_to_device(self, device: Device, command: str):
        self.pm.hook.send_command(device=device, command=command)

    def reset_device(self, device: Device):
        self.pm.hook.reset(device=device)