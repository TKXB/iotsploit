import os
import importlib.util
import pluggy
from spec import NetworkSpec

class NetworkPluginManager:
    def __init__(self):
        self.pm = pluggy.PluginManager("network_mgr")
        self.pm.add_hookspecs(NetworkSpec)
        self.load_plugins()

    def load_plugins(self):
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                filepath = os.path.join(plugin_dir, filename)
                module_name = os.path.splitext(filename)[0]
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register_plugin"):
                    module.register_plugin(self.pm)

    def connect(self, protocol, ip, user, passwd):
        connections = self.pm.hook.connect(protocol=protocol, ip=ip, user=user, passwd=passwd)
        return next((conn for conn in connections if conn is not None), None)

    def disconnect(self, protocol, connection):
        self.pm.hook.disconnect(protocol=protocol, connection=connection)

    def execute_command(self, protocol, connection, command):
        results = self.pm.hook.execute_command(protocol=protocol, connection=connection, command=command)
        return next((result for result in results if result is not None), None)
