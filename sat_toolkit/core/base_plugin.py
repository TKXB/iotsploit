from typing import Dict, Any

class BasePlugin:
    def __init__(self, info: Dict[str, Any] = None):
        self.info = info or {}

    def update_info(self, new_info: Dict[str, Any]):
        self.info.update(new_info)

    def get_info(self) -> Dict[str, Any]:
        return self.info

class BaseDeviceDriver:
    def __init__(self, info: Dict[str, Any] = None):
        self.info = info or {}
        self.device_interface = None
        self.supported_commands = {}  # format: {'command': 'description'}

    def update_info(self, new_info: Dict[str, Any]):
        self.info.update(new_info)

    def get_info(self) -> Dict[str, Any]:
        return self.info

    def get_supported_commands(self) -> Dict[str, str]:
        return self.supported_commands