import os
import importlib.util
import pluggy
from sat_toolkit.core.exploit_spec import ExploitPluginSpec

class ExploitPluginManager:
    def __init__(self):
        self.pm = pluggy.PluginManager("exploit_mgr")
        self.pm.add_hookspecs(ExploitPluginSpec)
        self.load_plugins()

    def load_plugins(self):
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        print(f"Loading plugins from {plugin_dir}")
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                filepath = os.path.join(plugin_dir, filename)
                module_name = os.path.splitext(filename)[0]
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register_plugin"):
                    module.register_plugin(self.pm)

    def initialize(self):
        self.pm.hook.initialize()

    def exploit(self, target):
        self.pm.hook.execute(target=target)

