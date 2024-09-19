from enum import Enum
from typing import Dict, Any

class DeviceType(Enum):
    USB = "USB"
    Wireless = "Wireless"
    Ethernet = "Ethernet"
    Serial = "Serial"

class Device:
    def __init__(self, device_id: str, name: str, device_type: DeviceType, attributes: Dict[str, Any]):
        self.device_id = device_id
        self.name = name
        self.device_type = device_type
        self.attributes = attributes

    def __repr__(self):
        return f"Device(id={self.device_id}, name={self.name}, type={self.device_type}, attributes={self.attributes})"

    def update_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def get_attribute(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)

class SerialDevice(Device):
    def __init__(self, device_id: str, name: str, port: str, baud_rate: int, attributes: Dict[str, Any]):
        super().__init__(device_id, name, DeviceType.Serial, attributes)
        self.port = port
        self.baud_rate = baud_rate

    def __repr__(self):
        return f"SerialDevice(id={self.device_id}, name={self.name}, port={self.port}, baud_rate={self.baud_rate}, attributes={self.attributes})"

    def set_baud_rate(self, new_baud_rate: int):
        self.baud_rate = new_baud_rate

    def get_port(self) -> str:
        return self.port

class USBDevice(Device):
    def __init__(self, device_id: str, name: str, vendor_id: str, product_id: str, attributes: Dict[str, Any]):
        super().__init__(device_id, name, DeviceType.USB, attributes)
        self.vendor_id = vendor_id
        self.product_id = product_id

    def __repr__(self):
        return f"USBDevice(id={self.device_id}, name={self.name}, vendor_id={self.vendor_id}, product_id={self.product_id}, attributes={self.attributes})"

    def get_vendor_id(self) -> str:
        return self.vendor_id

    def get_product_id(self) -> str:
        return self.product_id