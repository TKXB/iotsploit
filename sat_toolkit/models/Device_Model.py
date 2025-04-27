from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import Enum
from typing import Dict, Any, List, Optional, Type
from sqlalchemy import create_engine, Column, String, JSON, Enum as SQLAlchemyEnum, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import json
from .database import Base, engine, SessionLocal
from sat_toolkit.tools.xlogger import xlog
import datetime

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

class DeviceDBModel(Base):
    __tablename__ = 'devices'

    device_id = Column(String, primary_key=True)
    name = Column(String)
    device_type = Column(SQLAlchemyEnum(DeviceType))
    attributes = Column(JSON)

    __mapper_args__ = {
        'polymorphic_on': device_type,
        'polymorphic_identity': 'device'
    }

    def __init__(self, device: Device):
        self.device_id = device.device_id
        self.name = device.name
        self.device_type = device.device_type
        self.attributes = device.attributes

class SerialDeviceDBModel(DeviceDBModel):
    __mapper_args__ = {
        'polymorphic_identity': DeviceType.Serial,
    }

    def __init__(self, device: SerialDevice):
        super().__init__(device)
        self.attributes['port'] = device.port
        self.attributes['baud_rate'] = device.baud_rate

class USBDeviceDBModel(DeviceDBModel):
    __mapper_args__ = {
        'polymorphic_identity': DeviceType.USB,
    }

    def __init__(self, device: USBDevice):
        super().__init__(device)
        self.attributes['vendor_id'] = device.vendor_id
        self.attributes['product_id'] = device.product_id

class CANDeviceDBModel(DeviceDBModel):
    __mapper_args__ = {
        'polymorphic_identity': DeviceType.CAN,
    }

    def __init__(self, device: SocketCANDevice):
        super().__init__(device)
        self.attributes['interface'] = device.interface

class DeviceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        self.devices: Dict[str, Type[Device]] = {}
        Base.metadata.create_all(engine)
        self.Session = SessionLocal
        self.current_device = None

    @classmethod
    def get_instance(cls):
        return cls()

    def register_device(self, device_type: DeviceType, device_class: Type[Device]):
        self.devices[device_type] = device_class

    def create_device(self, device_type: DeviceType, **kwargs) -> Device:
        if device_type in self.devices:
            device_class = self.devices[device_type]
            device = device_class(**kwargs)
            self.save_device(device)
            return device
        raise ValueError(f"No device type registered for: {device_type}")

    def save_device(self, device: Device):
        session = self.Session()
        try:
            existing_device = session.query(DeviceDBModel).filter_by(device_id=device.device_id).first()
            if existing_device:
                xlog.info(f"Device with device_id '{device.device_id}' already exists. Skipping insertion.", name="device_model")
                return
            else:
                if isinstance(device, SerialDevice):
                    device_model = SerialDeviceDBModel(device)
                elif isinstance(device, USBDevice):
                    device_model = USBDeviceDBModel(device)
                elif isinstance(device, SocketCANDevice):
                    device_model = CANDeviceDBModel(device)
                else:
                    device_model = DeviceDBModel(device)
                session.add(device_model)
                session.commit()
                xlog.info(f"Device with device_id '{device.device_id}' has been added to the database.", name="device_model")
        except Exception as e:
            session.rollback()
            xlog.error(f"An error occurred while saving device '{device.device_id}': {e}", name="device_model")
            raise e
        finally:
            session.close()

    def get_all_devices(self) -> List[Dict[str, Any]]:
        session = self.Session()
        try:
            devices = session.query(DeviceDBModel).all()
            result = []
            for d in devices:
                # Create device object based on device type
                if d.device_type == DeviceType.Serial:
                    device = SerialDevice(
                        device_id=d.device_id,
                        name=d.name,
                        port=d.attributes.get('port', ''),
                        baud_rate=d.attributes.get('baud_rate', 115200),
                        attributes=d.attributes
                    )
                elif d.device_type == DeviceType.USB:
                    device = USBDevice(
                        device_id=d.device_id,
                        name=d.name,
                        vendor_id=d.attributes.get('vendor_id', ''),
                        product_id=d.attributes.get('product_id', ''),
                        attributes=d.attributes
                    )
                elif d.device_type == DeviceType.CAN:
                    device = SocketCANDevice(
                        device_id=d.device_id,
                        name=d.name,
                        interface=d.attributes.get('interface', 'can0'),
                        attributes=d.attributes
                    )
                else:
                    device = Device(
                        device_id=d.device_id,
                        name=d.name,
                        device_type=d.device_type,
                        attributes=d.attributes
                    )
                result.append(device.to_dict())
            return result
        except Exception as e:
            xlog.error(f"Error getting devices: {e}", name="device_model")
            return []
        finally:
            session.close()

    def parse_and_set_device_from_json(self, json_file_path):
        if not os.path.exists(json_file_path):
            xlog.error(f"File not found: {json_file_path}", name="device_model")
            return

        with open(json_file_path, 'r') as file:
            data = json.load(file)

        for device in data.get('devices', []):
            device_type = DeviceType(device.get('device_type', 'USB'))
            device_class = self.devices.get(device_type, Device)
            if not device_class:
                xlog.error(f"No device type registered for: {device_type}", name="device_model")
                continue

            device_data = {
                'device_id': device.get('device_id'),
                'name': device.get('name'),
                'attributes': device.get('attributes', {})
            }

            if device_type == DeviceType.Serial:
                device_data['port'] = device.get('port')
                device_data['baud_rate'] = device.get('baud_rate')
            elif device_type == DeviceType.USB:
                device_data['vendor_id'] = device.get('vendor_id')
                device_data['product_id'] = device.get('product_id')
            elif device_type == DeviceType.CAN:
                device_data['interface'] = device.get('interface', 'can0')

            device_instance = self.create_device(device_type, **device_data)
            self.current_device = device_instance

        xlog.debug("Parsed and created devices from JSON file", name="device_model")

    def get_current_device(self) -> Optional[Device]:
        return self.current_device

    def set_current_device(self, device: Device):
        self.current_device = device

class DeviceDriverState(Base):
    __tablename__ = 'device_driver_states'

    driver_name = Column(String, primary_key=True)
    enabled = Column(Boolean, default=True)
    description = Column(String, nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.datetime.now())

    def __init__(self, driver_name, enabled=True, description=None):
        self.driver_name = driver_name
        self.enabled = enabled
        self.description = description
        self.last_updated = datetime.datetime.now()

    def to_dict(self):
        return {
            "driver_name": self.driver_name,
            "enabled": self.enabled,
            "description": self.description,
            "last_updated": str(self.last_updated)
        }

if __name__ == "__main__":
    # Example usage
    device_manager = DeviceManager.get_instance()
    device_manager.register_device(DeviceType.Serial, SerialDevice)
    device_manager.register_device(DeviceType.USB, USBDevice)

    # Load devices from JSON file
    json_file_path = "path_to_your_json_file.json"
    device_manager.parse_and_set_device_from_json(json_file_path)

    # Retrieve and print all Devices from the database
    all_devices = device_manager.get_all_devices()
    for device in all_devices:
        print(f"Retrieved from DB: {device['name']}, ID: {device['device_id']}, Type: {device['device_type']}")
        print(json.dumps(device, indent=2))