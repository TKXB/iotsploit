import pluggy
import os
import importlib.util
import logging
from sat_toolkit.core.device_spec import DevicePluginSpec
from sat_toolkit.models.Device_Model import Device
from sat_toolkit.core.base_plugin import BaseDeviceDriver
from sat_toolkit.config import DEVICE_PLUGINS_DIR
from typing import Dict

logger = logging.getLogger(__name__)

class DevicePluginManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DevicePluginManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.debug("Initializing DeviceManager")
            self.pm = pluggy.PluginManager("device_mgr")
            self.pm.add_hookspecs(DevicePluginSpec)
            self.plugins = {}
            self.drivers = {}  # Store driver instances
            self.load_plugins()
            self._initialized = True
            logger.debug("DeviceManager initialized")

    def load_plugins(self):
        plugin_dir = os.path.join(os.path.dirname(__file__), DEVICE_PLUGINS_DIR)
        logger.debug(f"Loading device plugins from {plugin_dir}")
        for root, _, files in os.walk(plugin_dir):
            for filename in files:
                if filename.startswith("drv_") and filename.endswith(".py") and filename != "__init__.py":
                    self.load_plugin(os.path.join(root, filename))

    def load_plugin(self, filepath):
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Auto-register any class that inherits from BaseDeviceDriver
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, BaseDeviceDriver) and 
                attr != BaseDeviceDriver):
                driver_instance = attr()
                self.pm.register(driver_instance)
                self.plugins[module_name] = module
                self.drivers[module_name] = driver_instance  # Store the instance
                logger.info(f"Loaded device plugin: {module_name} ({attr_name})")
                break
    
    def get_driver_instance(self, plugin_name):
        return self.drivers.get(plugin_name)
    
    def register_plugin(self, plugin):
        self.pm.register(plugin)

    def list_devices(self):
        return list(self.plugins.keys())

    def scan_device(self, device: Device):
        print(f"Scanning device: {device.name}")
        self.pm.hook.scan(device=device)

    def scan_all_devices(self):
        logger.info("Scanning for all devices")
        scan_results = {}
        devices_found = False

        for plugin_name, plugin in self.plugins.items():
            logger.info(f"Scanning with plugin: {plugin_name}")
            result = self.pm.hook.scan(device=None)
            
            if result:
                devices_found = True
                if isinstance(result, list):
                    scan_results[plugin_name] = {
                        "status": "success",
                        "devices": [self.device_to_dict(device) for device in result if isinstance(device, Device)]
                    }
                elif isinstance(result, bool):
                    scan_results[plugin_name] = {
                        "status": "success",
                        "devices": ["Device detected"]
                    }
                else:
                    scan_results[plugin_name] = {
                        "status": "success",
                        "devices": [self.device_to_dict(result)] if isinstance(result, Device) else ["Unknown device detected"]
                    }
                logger.info(f"Devices found with plugin: {plugin_name}")
            else:
                scan_results[plugin_name] = {
                    "status": "failure",
                    "message": "No devices found"
                }
                logger.info(f"No devices found with plugin: {plugin_name}")

        return {
            "status": "success" if devices_found else "failure",
            "devices_found": devices_found,
            "message": "Device scan completed successfully." if devices_found else "No devices found.",
            "scan_results": scan_results
        }

    def device_to_dict(self, device):
        if not isinstance(device, Device):
            return str(device)
        return {
            "device_id": device.device_id,
            "name": device.name,
            "device_type": device.device_type.value,
            "attributes": device.attributes
        }

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
        # Add command validation
        for plugin in self.pm.get_plugins():
            if isinstance(plugin, BaseDeviceDriver):
                if command not in plugin.get_supported_commands().keys():
                    logger.warning(f"Command '{command}' not supported by device {device.name}")
                    return
                self.pm.hook.command(device=device, command=command)

    def reset_device(self, device: Device):
        print(f"Resetting device: {device.name}")
        self.pm.hook.reset(device=device)

    def close_device(self, device: Device):
        print(f"Closing device: {device.name}")
        self.pm.hook.close(device=device)

    def get_device_commands(self, device: Device) -> Dict[str, str]:
        """Get supported commands and their descriptions for a specific device/driver"""
        for plugin in self.pm.get_plugins():
            if isinstance(plugin, BaseDeviceDriver):
                return plugin.get_supported_commands()
        return {}

    def get_plugin_commands(self, plugin_name: str) -> Dict[str, str]:
        """Get supported commands for a specific plugin"""
        if plugin_name not in self.plugins:
            return {}
        
        plugin_module = self.plugins[plugin_name]
        for attr_name in dir(plugin_module):
            attr = getattr(plugin_module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, BaseDeviceDriver) and 
                attr != BaseDeviceDriver):
                return attr().get_supported_commands()
        return {}