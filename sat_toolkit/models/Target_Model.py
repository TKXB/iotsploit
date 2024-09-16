from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from sqlalchemy import create_engine, Column, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import json
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

# Base Target class
class Target(BaseModel, ABC):
    target_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        pass

# Component and Interface classes remain unchanged
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

# Vehicle class inherits from Target
class Vehicle(Target):
    ip_address: Optional[str] = None
    location: Optional[str] = None
    components: List[Component] = Field(default_factory=list)
    interfaces: List[Interface] = Field(default_factory=list)

    def get_info(self) -> Dict[str, Any]:
        info = super().model_dump()
        info.update({
            "ip_address": self.ip_address,
            "location": self.location,
            "components": [comp.model_dump() for comp in self.components],
            "interfaces": [intf.model_dump() for intf in self.interfaces],
        })
        return info

# SQLAlchemy database model using Single Table Inheritance
class TargetDBModel(Base):
    __tablename__ = 'targets'

    target_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    properties = Column(JSON)
    # Fields specific to Vehicle (nullable for other types)
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)
    components = Column(JSON, nullable=True)
    interfaces = Column(JSON, nullable=True)
    # Polymorphic attributes
    __mapper_args__ = {
        'polymorphic_on': type,
        'polymorphic_identity': 'target'
    }

    def __init__(self, target: Target):
        self.target_id = target.target_id
        self.name = target.name
        self.type = target.type
        self.status = target.status
        self.properties = target.properties

        # Assign subclass-specific fields
        if isinstance(target, Vehicle):
            self.ip_address = target.ip_address
            self.location = target.location
            self.components = [comp.model_dump() for comp in target.components]
            self.interfaces = [intf.model_dump() for intf in target.interfaces]
        # Additional handling for other Target types (e.g., Plane, Camera, Router)

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
            target_class = self.targets[target_type]
            target = target_class(**kwargs)
            self.save_target(target)
            return target
        raise ValueError(f"No target type registered for: {target_type}")

    def save_target(self, target: Target):
        session = self.Session()
        try:
            target_model = TargetDBModel(target)
            session.add(target_model)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_all_targets(self) -> List[Dict[str, Any]]:
        session = self.Session()
        try:
            targets = session.query(TargetDBModel).all()
            result = []
            for t in targets:
                target_info = {
                    "target_id": t.target_id,
                    "name": t.name,
                    "type": t.type,
                    "status": t.status,
                    "properties": t.properties
                }
                # Include Vehicle-specific fields if present
                if t.ip_address:
                    target_info["ip_address"] = t.ip_address
                if t.location:
                    target_info["location"] = t.location
                if t.components:
                    target_info["components"] = t.components
                if t.interfaces:
                    target_info["interfaces"] = t.interfaces
                result.append(target_info)
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

        for target in data.get('targets', []):
            target_type = target.get('type', 'unknown')
            target_class = self.targets.get(target_type, Target)
            if not target_class:
                logger.error(f"No target type registered for: {target_type}")
                continue

            # Get the fields of the target class
            model_fields = target_class.model_fields.keys()

            target_data = {}
            for key, value in target.items():
                if key in model_fields:
                    target_data[key] = value
                else:
                    target_data.setdefault('properties', {})[key] = value

            target_instance = self.create_target(target_type, **target_data)
            self.current_target = target_instance  # Set the current Target

        logger.info("Parsed and created targets from JSON file")

    def get_current_target(self) -> Optional[Target]:
        return self.current_target

    def set_current_target(self, target: Target):
        self.current_target = target

if __name__ == "__main__":
    # Example usage
    target_manager = TargetManager()
    target_manager.register_target("vehicle", Vehicle)

    # Register other Target types when defined
    # target_manager.register_target("plane", Plane)
    # target_manager.register_target("camera", Camera)
    # target_manager.register_target("router", Router)

    # Load targets from JSON file
    json_file_path = "path_to_your_json_file.json"  # Update with your actual JSON file path
    target_manager.parse_and_set_target_from_json(json_file_path)

    # Retrieve and print all Targets from the database
    all_targets = target_manager.get_all_targets()
    for t in all_targets:
        print(f"Retrieved from DB: {t['name']}, ID: {t['target_id']}, Type: {t['type']}")
        print(json.dumps(t, indent=2))
