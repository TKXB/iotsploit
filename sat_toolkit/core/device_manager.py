import pluggy
import os
import importlib.util
import logging
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.config import DEVICE_PLUGINS_DIR

logger = logging.getLogger(__name__)

class DevicePluginManager:
    def __init__(self):
        logger.info("Initializing DeviceManager")
        self.pm = pluggy.PluginManager("device_mgr")
        self.pm.add_hookspecs(DevicePluginSpec)
        self.plugins = {}
        self.load_plugins()
        logger.info("DeviceManager initialized")

    def load_plugins(self):
        plugin_dir = os.path.join(os.path.dirname(__file__), DEVICE_PLUGINS_DIR)
        logger.info(f"Loading device plugins from {plugin_dir}")
        for root, _, files in os.walk(plugin_dir):
            for filename in files:
                if filename.endswith(".py") and filename != "__init__.py":
                    self.load_plugin(os.path.join(root, filename))

    def load_plugin(self, filepath):
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "register_plugin"):
            module.register_plugin(self.pm)
            self.plugins[module_name] = module
            logger.info(f"Loaded device plugin: {module_name}")

    def register_plugin(self, plugin):
        self.pm.register(plugin)

    def list_devices(self):
        return list(self.plugins.keys())

    def scan_device(self, device: Device):
        print(f"Scanning device: {device.name}")
        self.pm.hook.scan(device=device)

    def initialize_device(self, device: Device):
        print(f"Initializing device: {device.name}")
        for plugin in self.pm.get_plugins():
            if isinstance(plugin, DevicePluginSpec):
                plugin.initialize(device=device)

    def connect_device(self, device: Device):
        print(f"Connecting to device: {device.name}")
        self.pm.hook.connect(device=device)

    def execute_on_target(self, device: Device, target: str):
        print(f"Executing on target: {target} using device: {device.name}")
        self.pm.hook.execute(device=device, target=target)

    def send_command_to_device(self, device: Device, command: str):
        print(f"Sending command to device: {device.name}")
        self.pm.hook.send_command(device=device, command=command)

    def reset_device(self, device: Device):
        print(f"Resetting device: {device.name}")
        self.pm.hook.reset(device=device)

    def close_device(self, device: Device):
        print(f"Closing device: {device.name}")
        self.pm.hook.close(device=device)