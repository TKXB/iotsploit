from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from sqlalchemy import create_engine, Column, String, JSON, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import json
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

# 基础的 Target 类
class Target(BaseModel, ABC):
    target_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        pass

# Component 和 Interface 类保持不变
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

# Vehicle 类继承自 Target
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

# 您可以类似地定义 Plane、Camera、Router 类，继承自 Target

# SQLAlchemy 数据库模型
class TargetDBModel(Base):
    __tablename__ = 'targets'

    target_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    properties = Column(JSON)
    # 多态属性
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

class VehicleDBModel(TargetDBModel):
    __tablename__ = 'vehicles'

    target_id = Column(String, ForeignKey('targets.target_id'), primary_key=True)
    ip_address = Column(String)
    location = Column(String)
    components = Column(JSON)
    interfaces = Column(JSON)

    __mapper_args__ = {
        'polymorphic_identity': 'vehicle',
    }

    def __init__(self, vehicle: Vehicle):
        super().__init__(vehicle)
        self.ip_address = vehicle.ip_address
        self.location = vehicle.location
        self.components = [comp.model_dump() for comp in vehicle.components]
        self.interfaces = [intf.model_dump() for intf in vehicle.interfaces]

# 类似地，创建 PlaneDBModel、CameraDBModel、RouterDBModel，继承自 TargetDBModel

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
            if isinstance(target, Vehicle):
                vehicle_model = VehicleDBModel(target)
                session.add(vehicle_model)
            # 在这里添加对其他 Target 类型的处理（例如 Plane、Camera、Router）
            else:
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
                if t.type == 'vehicle':
                    target = session.query(VehicleDBModel).filter_by(target_id=t.target_id).one()
                    result.append({
                        "target_id": target.target_id,
                        "name": target.name,
                        "type": target.type,
                        "status": target.status,
                        "ip_address": target.ip_address,
                        "location": target.location,
                        "properties": target.properties,
                        "components": target.components,
                        "interfaces": target.interfaces
                    })
                else:
                    # 对其他 Target 类型的处理
                    result.append({
                        "target_id": t.target_id,
                        "name": t.name,
                        "type": t.type,
                        "status": t.status,
                        "properties": t.properties
                    })
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

        for target in data.get('targets', []):  # Changed from 'devices' to 'targets'
            target_type = target.get('type', 'unknown')
            target_data = {
                "target_id": target.get('target_id', 'unknown_target'),  # Changed from 'device_id' to 'target_id'
                "name": target.get('name', 'Unknown Target'),
                "type": target_type,
                "properties": {}
            }

            # 收集属性
            for key, value in target.items():
                if key not in ['target_id', 'name', 'type']:  # Changed from 'device_id' to 'target_id'
                    if isinstance(value, dict):
                        target_data['properties'][key] = value
                    elif isinstance(value, list):
                        target_data[key] = value  # Components or interfaces
                    else:
                        target_data['properties'][key] = value

            target_instance = self.create_target(target_type, **target_data)
            self.current_target = target_instance  # 设置当前的 Target

        logger.info("Parsed and created targets from JSON file")

    def get_current_target(self) -> Optional[Target]:
        return self.current_target

    def set_current_target(self, target: Target):
        self.current_target = target

if __name__ == "__main__":
    # 示例用法
    target_manager = TargetManager()
    target_manager.register_target("vehicle", Vehicle)

    # 当定义了其他 Target 类型时，可以注册它们
    # target_manager.register_target("plane", Plane)
    # target_manager.register_target("camera", Camera)
    # target_manager.register_target("router", Router)

    # 使用简化的系统创建一个 Target
    vehicle_data = {
        "target_id": "vehicle_001",
        "name": "Tesla Model 3",
        "type": "vehicle",
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

    # 从数据库检索所有的 Target
    all_targets = target_manager.get_all_targets()
    for t in all_targets:
        print(f"Retrieved from DB: {t['name']}, ID: {t['target_id']}, Type: {t['type']}")
