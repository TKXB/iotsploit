from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from sqlalchemy import create_engine, Column, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import json
from .database import Base, engine, SessionLocal
from sat_toolkit.tools.xlogger import xlog

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

# ADBDevice class for components that can be accessed via ADB
class ADBDevice(Component):
    adb_serial_id: Optional[str] = None
    usb_vendor_id: Optional[str] = None
    usb_product_id: Optional[str] = None
    
    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({
            "adb_serial_id": self.adb_serial_id,
            "usb_vendor_id": self.usb_vendor_id,
            "usb_product_id": self.usb_product_id
        })
        return info

# Camera component for camera devices
class CameraComponent(Component):
    resolution: Optional[str] = None
    fps: Optional[int] = None
    codec: Optional[str] = None
    rtsp_url: Optional[str] = None
    
    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({
            "resolution": self.resolution,
            "fps": self.fps,
            "codec": self.codec,
            "rtsp_url": self.rtsp_url
        })
        return info

# Sensor component for various sensors
class SensorComponent(Component):
    sensor_type: Optional[str] = None  # temperature, pressure, accelerometer, etc.
    unit: Optional[str] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    accuracy: Optional[float] = None
    
    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({
            "sensor_type": self.sensor_type,
            "unit": self.unit,
            "range_min": self.range_min,
            "range_max": self.range_max,
            "accuracy": self.accuracy
        })
        return info

# Network component for network interfaces
class NetworkComponent(Component):
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    interface_type: Optional[str] = None  # ethernet, wifi, cellular
    bandwidth: Optional[str] = None
    
    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "interface_type": self.interface_type,
            "bandwidth": self.bandwidth
        })
        return info

# ECU component for automotive electronic control units
class ECUComponent(Component):
    ecu_type: Optional[str] = None  # engine, transmission, brake, etc.
    protocol: Optional[str] = None  # CAN, LIN, FlexRay
    address: Optional[str] = None
    firmware_version: Optional[str] = None
    
    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({
            "ecu_type": self.ecu_type,
            "protocol": self.protocol,
            "address": self.address,
            "firmware_version": self.firmware_version
        })
        return info

# Component Factory for creating components based on type
class ComponentFactory:
    """Factory class for creating different types of components"""
    
    _component_types = {
        'adb_device': ADBDevice,
        'camera': CameraComponent,
        'sensor': SensorComponent,
        'network': NetworkComponent,
        'ecu': ECUComponent,
        'infotainment': ADBDevice,  # Infotainment systems often use ADB
        'generic': Component,  # Fallback for unknown types
    }
    
    @classmethod
    def register_component_type(cls, type_name: str, component_class: Type[Component]):
        """Register a new component type"""
        cls._component_types[type_name] = component_class
        xlog.info(f"Registered component type: {type_name}", name="component_factory")
    
    @classmethod
    def create_component(cls, comp_data: Dict[str, Any]) -> Component:
        """Create a component instance based on the component data"""
        comp_type = comp_data.get('type', 'generic')
        component_class = cls._component_types.get(comp_type, Component)
        
        try:
            # Extract fields that are specific to the component class
            component_fields = component_class.model_fields.keys()
            filtered_data = {}
            
            for key, value in comp_data.items():
                if key in component_fields:
                    filtered_data[key] = value
                else:
                    # Put unknown fields into properties
                    filtered_data.setdefault('properties', {})[key] = value
            
            # Ensure required fields have defaults
            filtered_data.setdefault('component_id', comp_data.get('component_id', ''))
            filtered_data.setdefault('name', comp_data.get('name', ''))
            filtered_data.setdefault('type', comp_type)
            filtered_data.setdefault('status', 'active')
            filtered_data.setdefault('properties', {})
            
            component = component_class(**filtered_data)
            xlog.debug(f"Created {comp_type} component: {component.name}", name="component_factory")
            return component
            
        except Exception as e:
            xlog.error(f"Error creating component of type {comp_type}: {str(e)}", name="component_factory")
            xlog.debug(f"Component data: {comp_data}", name="component_factory")
            # Fallback to generic component
            return Component(
                component_id=comp_data.get('component_id', ''),
                name=comp_data.get('name', ''),
                type=comp_type,
                status=comp_data.get('status', 'active'),
                properties=comp_data.get('properties', {})
            )
    
    @classmethod
    def get_supported_types(cls) -> List[str]:
        """Get list of supported component types"""
        return list(cls._component_types.keys())

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
    
    def get_adb_devices(self) -> Dict[str, ADBDevice]:
        """Returns a dictionary of ADB devices keyed by their names"""
        adb_devices = {}
        for component in self.components:
            if isinstance(component, ADBDevice):
                adb_devices[component.name] = component
        return adb_devices
    
    def get_adb_device_by_name(self, name: str) -> Optional[ADBDevice]:
        """Get an ADB device component by name"""
        for component in self.components:
            if isinstance(component, ADBDevice) and component.name == name:
                return component
        return None

    def get_adb_device_by_type(self, device_type: str) -> Optional[ADBDevice]:
        """Get an ADB device component by its type"""
        for component in self.components:
            if isinstance(component, ADBDevice) and component.type == device_type:
                return component
        return None
    
    def get_components_by_type(self, component_type: str) -> List[Component]:
        """Get all components of a specific type"""
        return [comp for comp in self.components if comp.type == component_type]
    
    def get_component_by_id(self, component_id: str) -> Optional[Component]:
        """Get a component by its ID"""
        for component in self.components:
            if component.component_id == component_id:
                return component
        return None
    
    def get_cameras(self) -> List[CameraComponent]:
        """Get all camera components"""
        return [comp for comp in self.components if isinstance(comp, CameraComponent)]
    
    def get_sensors(self) -> List[SensorComponent]:
        """Get all sensor components"""
        return [comp for comp in self.components if isinstance(comp, SensorComponent)]
    
    def get_network_components(self) -> List[NetworkComponent]:
        """Get all network components"""
        return [comp for comp in self.components if isinstance(comp, NetworkComponent)]
    
    def get_ecus(self) -> List[ECUComponent]:
        """Get all ECU components"""
        return [comp for comp in self.components if isinstance(comp, ECUComponent)]
    
    def add_component(self, component: Component):
        """Add a component to the vehicle"""
        # Check if component with same ID already exists
        existing = self.get_component_by_id(component.component_id)
        if existing:
            raise ValueError(f"Component with ID {component.component_id} already exists")
        self.components.append(component)
    
    def remove_component(self, component_id: str) -> bool:
        """Remove a component by ID"""
        for i, comp in enumerate(self.components):
            if comp.component_id == component_id:
                del self.components[i]
                return True
        return False

# SQLAlchemy database model using Single Table Inheritance
class TargetDBModel(Base):
    __tablename__ = 'targets'  # Ensure this is different from the devices table

    target_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    properties = Column(JSON)
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)
    components = Column(JSON, nullable=True)
    interfaces = Column(JSON, nullable=True)

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
        # Do not initialize subclass-specific fields here


class VehicleDBModel(TargetDBModel):
    __mapper_args__ = {
        'polymorphic_identity': 'vehicle',
    }

    def __init__(self, target: Vehicle):
        super().__init__(target)
        self.ip_address = target.ip_address
        self.location = target.location
        self.components = [comp.model_dump() for comp in target.components]
        self.interfaces = [intf.model_dump() for intf in target.interfaces]


class TargetManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TargetManager, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        self.targets: Dict[str, Type[Target]] = {}
        Base.metadata.create_all(engine)
        self.Session = SessionLocal
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
            existing_target = session.query(TargetDBModel).filter_by(target_id=target.target_id).first()
            if existing_target:
                xlog.info(f"Target with target_id '{target.target_id}' already exists. Updating record with new values.", name="target_model")
                # Update base fields
                existing_target.name = target.name
                existing_target.status = target.status
                existing_target.properties = target.properties

                # If the target is a Vehicle, update vehicle-specific fields
                if isinstance(target, Vehicle):
                    existing_target.ip_address = target.ip_address
                    existing_target.location = target.location
                    existing_target.components = [comp.model_dump() for comp in target.components]
                    existing_target.interfaces = [intf.model_dump() for intf in target.interfaces]

                # Commit the updates
                session.commit()
            else:
                # Create a new record if it doesn't exist
                if isinstance(target, Vehicle):
                    target_model = VehicleDBModel(target)
                else:
                    target_model = TargetDBModel(target)
                session.add(target_model)
                session.commit()
                xlog.info(f"Target with target_id '{target.target_id}' has been added to the database.", name="target_model")
        except Exception as e:
            session.rollback()
            xlog.error(f"An error occurred while saving target '{target.target_id}': {e}", name="target_model")
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
                # Include Vehicle-specific fields if applicable
                if isinstance(t, VehicleDBModel):
                    target_info["ip_address"] = t.ip_address
                    target_info["location"] = t.location
                    target_info["components"] = t.components
                    target_info["interfaces"] = t.interfaces
                result.append(target_info)
            return result
        finally:
            session.close()


    def parse_and_set_target_from_json(self, json_file_path):
        xlog.debug(f"Reading JSON file from: {json_file_path}", name="target_model")
        if not os.path.exists(json_file_path):
            xlog.error(f"File not found: {json_file_path}", name="target_model")
            return

        with open(json_file_path, 'r') as file:
            data = json.load(file)

        xlog.debug(f"JSON data: {data}", name="target_model")

        for target in data.get('targets', []):
            target_type = target.get('type', 'unknown')
            target_class = self.targets.get(target_type, Target)
            if not target_class:
                xlog.error(f"No target type registered for: {target_type}", name="target_model")
                continue

            # Process components
            components = []
            if 'components' in target:
                for comp in target.get('components', []):
                    component = ComponentFactory.create_component(comp)
                    components.append(component)
                
                # Replace components list in target data with processed components
                target['components'] = components

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

        xlog.debug("Parsed and created targets from JSON file", name="target_model")

    def get_current_target(self) -> Optional[Target]:
        return self.current_target

    def set_current_target(self, target: Target):
        self.current_target = target

    def update_target(self, target_data: Dict[str, Any]) -> bool:
        """
        Update an existing target in the database.
        
        Args:
            target_data: Dictionary containing target information to update
        
        Returns:
            bool: True if update was successful, False otherwise
        """
        session = self.Session()
        try:
            # Find the existing target
            target_id = target_data.get('target_id')
            if not target_id:
                xlog.error("No target_id provided in update data", name="target_model")
                return False
            
            existing_target = session.query(TargetDBModel).filter_by(target_id=target_id).first()
            if not existing_target:
                xlog.error(f"No target found with target_id: {target_id}", name="target_model")
                return False
            
            # Update the fields (skip target_id as it's the primary key)
            for key, value in target_data.items():
                if key == 'target_id':
                    continue  # Skip target_id as it shouldn't be updated
                if hasattr(existing_target, key):
                    xlog.debug(f"Updating {key} to {value}", name="target_model")
                    setattr(existing_target, key, value)
                else:
                    xlog.warning(f"Target does not have attribute: {key}", name="target_model")
            
            session.commit()
            xlog.info(f"Successfully updated target {target_id}", name="target_model")
            return True
        
        except Exception as e:
            session.rollback()
            xlog.error(f"Error updating target: {str(e)}", name="target_model")
            return False
        
        finally:
            session.close()

    def create_target_instance(self, target_dict):
        """
        Creates a Vehicle instance from a target dictionary
        """
        if isinstance(target_dict, Vehicle):
            return target_dict
        
        if target_dict.get('type') != 'vehicle':
            raise ValueError(f"Unsupported target type: {target_dict.get('type')}")
        
        # Create a properly formatted dictionary with all required fields
        vehicle_data = {
            'target_id': target_dict['target_id'],
            'name': target_dict['name'],
            'type': target_dict['type'],
            'status': target_dict.get('status', 'active'),
            'properties': target_dict.get('properties', {}),
            'ip_address': target_dict.get('ip_address'),
            'location': target_dict.get('location'),
        }

        # Process components
        components = []
        if 'components' in target_dict:
            for comp in target_dict['components']:
                if isinstance(comp, Component):
                    components.append(comp)
                elif isinstance(comp, dict):
                    component = ComponentFactory.create_component(comp)
                    components.append(component)
        
        vehicle_data['components'] = components

        # Handle interfaces if present
        if 'interfaces' in target_dict:
            vehicle_data['interfaces'] = [
                Interface(**intf) if isinstance(intf, dict) else intf 
                for intf in target_dict['interfaces']
            ]
        else:
            vehicle_data['interfaces'] = []

        try:
            # Create Vehicle instance using the properly formatted data
            vehicle = Vehicle(**vehicle_data)
            xlog.debug(f"Created Vehicle instance: {vehicle}", name="target_model")
            return vehicle
        except Exception as e:
            xlog.error(f"Error creating Vehicle instance: {str(e)}", name="target_model")
            xlog.debug(f"Vehicle data: {vehicle_data}", name="target_model")
            raise

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
