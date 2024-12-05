from enum import Enum
from typing import Dict, Any, List, Optional, Type
from sqlalchemy import create_engine, Column, String, JSON, Enum as SQLAlchemyEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import json
import logging
from .database import Base, engine, SessionLocal

logger = logging.getLogger(__name__)

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

class DeviceDBModel(Base):
    __tablename__ = 'devices'  # Ensure this is different from the targets table

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
                logger.info(f"Device with device_id '{device.device_id}' already exists. Skipping insertion.")
                return
            else:
                if isinstance(device, SerialDevice):
                    device_model = SerialDeviceDBModel(device)
                elif isinstance(device, USBDevice):
                    device_model = USBDeviceDBModel(device)
                else:
                    device_model = DeviceDBModel(device)
                session.add(device_model)
                session.commit()
                logger.info(f"Device with device_id '{device.device_id}' has been added to the database.")
        except Exception as e:
            session.rollback()
            logger.error(f"An error occurred while saving device '{device.device_id}': {e}")
            raise e
        finally:
            session.close()

    def get_all_devices(self) -> List[Dict[str, Any]]:
        session = self.Session()
        try:
            devices = session.query(DeviceDBModel).all()
            result = []
            for d in devices:
                device_info = {
                    "device_id": d.device_id,
                    "name": d.name,
                    "device_type": d.device_type.value,
                    "attributes": d.attributes
                }
                result.append(device_info)
            return result
        finally:
            session.close()

    def parse_and_set_device_from_json(self, json_file_path):
        if not os.path.exists(json_file_path):
            logger.error(f"File not found: {json_file_path}")
            return

        with open(json_file_path, 'r') as file:
            data = json.load(file)

        for device in data.get('devices', []):
            device_type = DeviceType(device.get('device_type', 'USB'))
            device_class = self.devices.get(device_type, Device)
            if not device_class:
                logger.error(f"No device type registered for: {device_type}")
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

            device_instance = self.create_device(device_type, **device_data)
            self.current_device = device_instance

        logger.debug("Parsed and created devices from JSON file")

    def get_current_device(self) -> Optional[Device]:
        return self.current_device

    def set_current_device(self, device: Device):
        self.current_device = device

if __name__ == "__main__":
    # Example usage
    device_manager = DeviceManager.get_instance()
    device_manager.register_device(DeviceType.Serial, SerialDevice)
    device_manager.register_device(DeviceType.USB, USBDevice)

    # Load devices from JSON file
    json_file_path = "path_to_your_json_file.json"  # Update with your actual JSON file path
    device_manager.parse_and_set_device_from_json(json_file_path)

    # Retrieve and print all Devices from the database
    all_devices = device_manager.get_all_devices()
    for d in all_devices:
        print(f"Retrieved from DB: {d['name']}, ID: {d['device_id']}, Type: {d['device_type']}")
        print(json.dumps(d, indent=2))