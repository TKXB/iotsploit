from enum import Enum

class DeviceType(Enum):
    USB = "USB"
    Wireless = "Wireless"
    Ethernet = "Ethernet"
    Serial = "Serial"

class Device:
    def __init__(self, device_id: str, device_name: str, device_type: DeviceType, attributes: dict):
        self.device_id = device_id
        self.name = device_name
        self.device_type = device_type
        self.attributes = attributes

    def __repr__(self):
        return f"Device(device_id={self.device_id}, device_type={self.device_type}, attributes={self.attributes})"