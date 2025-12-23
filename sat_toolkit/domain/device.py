from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict

from dataclasses_json import dataclass_json


class DeviceType(Enum):
    USB = "USB"
    Wireless = "Wireless"
    Ethernet = "Ethernet"
    Serial = "Serial"
    CAN = "CAN"


@dataclass_json
@dataclass
class Device:
    device_id: str
    name: str
    device_type: DeviceType
    attributes: Dict[str, Any] = field(default_factory=dict)

    def update_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def get_attribute(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)


@dataclass_json
@dataclass
class SerialDevice(Device):
    device_id: str = field()
    name: str = field()
    device_type: DeviceType = field(default=DeviceType.Serial)
    attributes: Dict[str, Any] = field(default_factory=dict)
    port: str = field(default="")
    baud_rate: int = field(default=115200)

    def set_baud_rate(self, new_baud_rate: int):
        self.baud_rate = new_baud_rate

    def get_port(self) -> str:
        return self.port


@dataclass_json
@dataclass
class USBDevice(Device):
    device_id: str = field()
    name: str = field()
    device_type: DeviceType = field(default=DeviceType.USB)
    attributes: Dict[str, Any] = field(default_factory=dict)
    vendor_id: str = field(default="")
    product_id: str = field(default="")


@dataclass_json
@dataclass
class SocketCANDevice(Device):
    device_id: str = field()
    name: str = field()
    device_type: DeviceType = field(default=DeviceType.CAN)
    attributes: Dict[str, Any] = field(default_factory=dict)
    interface: str = field(default="can0")


