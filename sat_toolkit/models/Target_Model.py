from pydantic import BaseModel, IPvAnyAddress, conint, constr, Literal
from typing import List, Optional

class Component(BaseModel):
    component_id: str
    name: str
    type: Literal['module', 'cpu', 'flash']
    status: Literal['active', 'inactive']
    firmware_version: Optional[str] = None
    protocol: Optional[str] = None
    architecture: Optional[str] = None
    clock_speed_mhz: Optional[int] = None
    capacity_mb: Optional[int] = None

class Interface(BaseModel):
    interface_id: str
    name: str
    type: Literal['jtag', 'uart']
    status: Literal['active', 'inactive']
    pinout: Optional[str] = None
    baud_rate: Optional[int] = None

class Device(BaseModel):
    device_id: str
    name: str
    type: Literal['sensor', 'actuator', 'gateway']
    location: Optional[str] = None
    status: Literal['active', 'inactive']
    ip_address: IPvAnyAddress
    components: List[Component]
    interfaces: List[Interface]

class IoTSystem(BaseModel):
    devices: List[Device]

# Example usage
iot_data = {
    "devices": [
        {
            "device_id": "device_001",
            "name": "Temperature Sensor",
            "type": "sensor",
            "location": "Living Room",
            "status": "active",
            "ip_address": "192.168.1.10",
            "components": [
                {
                    "component_id": "comp_001",
                    "name": "Temperature Module",
                    "type": "module",
                    "status": "active",
                    "firmware_version": "1.0.0",
                    "protocol": "Zigbee"
                },
                {
                    "component_id": "comp_002",
                    "name": "CPU",
                    "type": "cpu",
                    "status": "active",
                    "architecture": "ARM Cortex-M4",
                    "clock_speed_mhz": 120
                },
                {
                    "component_id": "comp_003",
                    "name": "Flash Memory",
                    "type": "flash",
                    "status": "active",
                    "capacity_mb": 512
                }
            ],
            "interfaces": [
                {
                    "interface_id": "intf_001",
                    "name": "JTAG",
                    "type": "jtag",
                    "status": "active",
                    "pinout": "standard"
                },
                {
                    "interface_id": "intf_002",
                    "name": "UART",
                    "type": "uart",
                    "status": "active",
                    "baud_rate": 115200
                }
            ]
        },
    ]
}

try:
    iot_system = IoTSystem(**iot_data)
    print(iot_system)
except ValidationError as e:
    print(e.json())