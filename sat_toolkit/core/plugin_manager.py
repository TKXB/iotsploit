import os
import importlib.util
import pluggy
import logging

from sat_toolkit.core.exploit_spec import ExploitPluginSpec
logger = logging.getLogger(__name__)

class ExploitPluginManager:
    def __init__(self):
        self.pm = pluggy.PluginManager("exploit_mgr")
        self.pm.add_hookspecs(ExploitPluginSpec)
        self.plugins = {}
        self.load_plugins()

    def load_plugins(self):
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        logger.info(f"Loading plugins from {plugin_dir}")
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                self.load_plugin(os.path.join(plugin_dir, filename))

    def load_plugin(self, filepath):
        module_name = os.path.splitext(os.path.basename(filepath))[0]
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "register_plugin"):
            module.register_plugin(self.pm)
            self.plugins[module_name] = module
            logger.info(f"Loaded plugin: {module_name}")

    def unload_plugin(self, plugin_name):
        if plugin_name in self.plugins:
            del self.plugins[plugin_name]
            logger.info(f"Unloaded plugin: {plugin_name}")

    def initialize(self):
        self.pm.hook.initialize()

    def exploit(self):
        self.pm.hook.execute()