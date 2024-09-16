from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from sqlalchemy import create_engine, Column, String, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import json
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

class Target(BaseModel, ABC):
    target_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        pass

class Component(BaseModel):
    component_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    def get_info(self) -> Dict[str, Any]:
        return self.model_dump()

class Interface(BaseModel):
    interface_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    def get_info(self) -> Dict[str, Any]:
        return self.model_dump()

class Vehicle(Target):
    ip_address: Optional[str] = None
    location: Optional[str] = None
    components: List[Component] = Field(default_factory=list)
    interfaces: List[Interface] = Field(default_factory=list)

    def get_info(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "ip_address": self.ip_address,
            "location": self.location,
            "properties": self.properties,
            "components": [comp.model_dump() for comp in self.components],
            "interfaces": [intf.model_dump() for intf in self.interfaces],
        }

# SQLAlchemy Models
class ComponentModel(Base):
    __tablename__ = 'components'

    component_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    properties = Column(JSON)

    def __init__(self, component: Component):
        self.component_id = component.component_id
        self.name = component.name
        self.type = component.type
        self.status = component.status
        self.properties = component.properties

class InterfaceModel(Base):
    __tablename__ = 'interfaces'

    interface_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    properties = Column(JSON)

    def __init__(self, interface: Interface):
        self.interface_id = interface.interface_id
        self.name = interface.name
        self.type = interface.type
        self.status = interface.status
        self.properties = interface.properties

class VehicleDBModel(Base):
    __tablename__ = 'vehicles'

    target_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    ip_address = Column(String)
    location = Column(String)
    properties = Column(JSON)
    components = Column(JSON)
    interfaces = Column(JSON)

    def __init__(self, vehicle: Vehicle):
        self.target_id = vehicle.target_id
        self.name = vehicle.name
        self.type = vehicle.type
        self.status = vehicle.status
        self.ip_address = vehicle.ip_address
        self.location = vehicle.location
        self.properties = vehicle.properties
        self.components = [comp.model_dump() for comp in vehicle.components]
        self.interfaces = [intf.model_dump() for intf in vehicle.interfaces]
        

class TargetManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TargetManager, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        self.targets: Dict[str, Type[Target]] = {}
        db_path = os.path.join(os.path.dirname(__file__), 'target_database.sqlite')
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.current_target = None

    @classmethod
    def get_instance(cls):
        return cls()

    def register_target(self, target_type: str, target_class: Type[Target]):
        self.targets[target_type] = target_class

    def create_target(self, target_type: str, **kwargs) -> Target:
        if target_type in self.targets:
            target = self.targets[target_type](**kwargs)
            self.save_target(target)
            return target
        raise ValueError(f"No target type registered for: {target_type}")

    def save_target(self, target: Target):
        session = self.Session()
        try:
            if isinstance(target, Vehicle):
                vehicle_model = VehicleDBModel(target)
                session.add(vehicle_model)
                for component in target.components:
                    component_model = ComponentModel(component)
                    session.add(component_model)
                for interface in target.interfaces:
                    interface_model = InterfaceModel(interface)
                    session.add(interface_model)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_all_vehicles(self) -> List[Dict[str, Any]]:
        session = self.Session()
        try:
            vehicles = session.query(VehicleDBModel).all()
            result = [
                {
                    "target_id": v.target_id,
                    "name": v.name,
                    "type": v.type,
                    "status": v.status,
                    "ip_address": v.ip_address,
                    "location": v.location,
                    "properties": v.properties,
                    "components": v.components,
                    "interfaces": v.interfaces
                }
                for v in vehicles
            ]
            return result
        finally:
            session.close()

    def parse_and_set_target_from_json(self, json_file_path):
        logger.debug(f"Reading JSON file from: {json_file_path}")
        if not os.path.exists(json_file_path):
            logger.error(f"File not found: {json_file_path}")
            return

        with open(json_file_path, 'r') as file:
            data = json.load(file)
        
        logger.debug(f"JSON data: {data}")

        for device in data.get('devices', []):
            vehicle_data = {
                "target_id": device.get('device_id', 'unknown_device'),
                "name": device.get('name', 'Unknown Device'),
                "type": device.get('type', 'unknown'),
                "ip_address": device.get('ip_address'),
                "location": device.get('location'),
                "properties": {},
                "components": [],
                "interfaces": []
            }

            for key, value in device.items():
                if key not in ['device_id', 'name', 'type', 'ip_address', 'location']:
                    if isinstance(value, dict):
                        vehicle_data['properties'][key] = value
                    elif isinstance(value, list):
                        if key == 'components':
                            vehicle_data['components'] = [Component(**item) for item in value]
                        elif key == 'interfaces':
                            vehicle_data['interfaces'] = [Interface(**item) for item in value]
                        else:
                            vehicle_data['properties'][key] = value
                    else:
                        vehicle_data['properties'][key] = value

            target = self.create_target("vehicle", **vehicle_data)
            self.current_target = target  # Set the current target

        logger.info("Parsed and created targets from JSON file")

    def get_current_target(self) -> Optional[Target]:
        return self.current_target

    def set_current_target(self, target: Target):
        self.current_target = target

if __name__ == "__main__":
    # Example usage
    target_manager = TargetManager()
    target_manager.register_target("vehicle", Vehicle)

    # Create a target using the simplified system
    vehicle_data = {
        "target_id": "vehicle_001",
        "name": "Tesla Model 3",
        "type": "electric_car",
        "ip_address": "192.168.1.10",
        "location": "Garage",
        "properties": {
            "model_year": 2023,
            "battery_capacity": "75 kWh"
        },
        "components": [
            {
                "component_id": "comp_001",
                "name": "Electric Motor",
                "type": "motor",
                "properties": {
                    "power": "283 kW",
                    "torque": "450 Nm"
                }
            }
        ],
        "interfaces": [
            {
                "interface_id": "intf_001",
                "name": "OBD-II",
                "type": "diagnostic",
                "properties": {
                    "protocol": "CAN"
                }
            }
        ]
    }

    vehicle = target_manager.create_target("vehicle", **vehicle_data)
    print(vehicle.get_info())

    # Retrieve all vehicles from the database
    all_vehicles = target_manager.get_all_vehicles()
    for v in all_vehicles:
        print(f"Retrieved from DB: {v['name']}, ID: {v['target_id']}")