from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from sqlalchemy import create_engine, Column, String, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

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

class VehicleModel(Base):
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

class TargetFactory:
    @staticmethod
    def create_target(target_type: str, **kwargs) -> Target:
        if target_type == "vehicle":
            return Vehicle(**kwargs)
        # Add more target types here as needed
        raise ValueError(f"Unknown target type: {target_type}")

class TargetManager:
    def __init__(self):
        self.targets: Dict[str, Type[Target]] = {}
        db_path = os.path.join(os.path.dirname(__file__), 'target_database.sqlite')
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

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
                vehicle_model = VehicleModel(target)
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
            vehicles = session.query(VehicleModel).all()
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