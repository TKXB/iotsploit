from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field, SerializeAsAny


class Target(BaseModel, ABC):
    target_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    location: Optional[str] = None
    # SerializeAsAny keeps subclass fields: without it pydantic serializes these
    # against the *declared* type and silently drops adb_serial_id and friends,
    # which is why every caller used to re-dump the items one by one.
    components: SerializeAsAny[List["Component"]] = Field(default_factory=list)
    interfaces: SerializeAsAny[List["Interface"]] = Field(default_factory=list)

    def get_info(self) -> Dict[str, Any]:
        return self.model_dump()

    def get_ecu_ip(self, ecu: str) -> Optional[str]:
        """Return the configured IP of the ECU component whose name matches `ecu`.

        ECUs are modeled as components selected by name ("TCAM"/"DHU"/"VGM").
        The IP is read from the component's free-form ``properties.ip_address``,
        falling back to a typed ``ip_address`` field (e.g. NetworkComponent).
        Returns None when the ECU has no configured IP.
        """
        name = (ecu or "").upper()
        for comp in self.components:
            if comp.name.upper() == name:
                ip = comp.properties.get("ip_address") if isinstance(comp.properties, dict) else None
                return ip or getattr(comp, "ip_address", None)
        return None


class Component(BaseModel):
    component_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    def get_info(self) -> Dict[str, Any]:
        return self.model_dump()


class ADBDevice(Component):
    adb_serial_id: Optional[str] = None
    usb_vendor_id: Optional[str] = None
    usb_product_id: Optional[str] = None


class CameraComponent(Component):
    resolution: Optional[str] = None
    fps: Optional[int] = None
    codec: Optional[str] = None
    rtsp_url: Optional[str] = None


class SensorComponent(Component):
    sensor_type: Optional[str] = None
    unit: Optional[str] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    accuracy: Optional[float] = None


class NetworkComponent(Component):
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    interface_type: Optional[str] = None
    bandwidth: Optional[str] = None



class ECUComponent(Component):
    ecu_type: Optional[str] = None
    protocol: Optional[str] = None
    address: Optional[str] = None
    firmware_version: Optional[str] = None


class ComponentFactory:
    _component_types: Dict[str, Type[Component]] = {
        "adb_device": ADBDevice,
        "camera": CameraComponent,
        "sensor": SensorComponent,
        "network": NetworkComponent,
        "ecu": ECUComponent,
        "infotainment": ADBDevice,
        "generic": Component,
    }

    @classmethod
    def register_component_type(cls, type_name: str, component_class: Type[Component]):
        cls._component_types[type_name] = component_class

    @classmethod
    def create_component(cls, comp_data: Dict[str, Any]) -> Component:
        comp_type = comp_data.get("type", "generic")
        component_class = cls._component_types.get(comp_type, Component)

        component_fields = component_class.model_fields.keys()
        filtered_data: Dict[str, Any] = {}
        for key, value in comp_data.items():
            if key in component_fields:
                filtered_data[key] = value
            else:
                filtered_data.setdefault("properties", {})[key] = value

        filtered_data.setdefault("component_id", comp_data.get("component_id", ""))
        filtered_data.setdefault("name", comp_data.get("name", ""))
        filtered_data.setdefault("type", comp_type)
        filtered_data.setdefault("status", "active")
        filtered_data.setdefault("properties", {})
        return component_class(**filtered_data)

    @classmethod
    def get_supported_types(cls) -> List[str]:
        return list(cls._component_types.keys())


class Interface(BaseModel):
    interface_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)

    def get_info(self) -> Dict[str, Any]:
        return self.model_dump()


class Vehicle(Target):
    """Vehicle target with ADB-specific helper methods."""

    # -------- ADB helpers (used by ADB_Mgr / UI) --------
    def get_adb_devices(self) -> Dict[str, ADBDevice]:
        """Return ADB devices keyed by component name."""
        adb_devices: Dict[str, ADBDevice] = {}
        for comp in self.components:
            if isinstance(comp, ADBDevice):
                adb_devices[comp.name] = comp
        return adb_devices

    def get_adb_device_by_name(self, name: str) -> Optional[ADBDevice]:
        return self.get_adb_devices().get(name)

    def get_adb_device_by_type(self, type_name: str) -> Optional[ADBDevice]:
        """Find first ADBDevice whose component type matches."""
        for comp in self.components:
            if isinstance(comp, ADBDevice) and comp.type == type_name:
                return comp
        return None

    def export_for_adb(self) -> Dict[str, Any]:
        """
        Export minimal information useful for ADB tooling.
        Keeps backward compatibility with callers that read target-level adb configuration.
        """
        return {
            "target_id": self.target_id,
            "name": self.name,
            "ip_address": self.ip_address,
            "adb_devices": {k: v.get_info() for k, v in self.get_adb_devices().items()},
        }


class GenericTarget(Target):
    """Generic target for non-vehicle devices (ECU, IoT, phone, router, camera, etc)."""


# Target type registry
TARGET_TYPES = {
    "vehicle": "Vehicle",
    "ecu": "ECU",
    "iot": "IoT Device",
    "phone": "Phone/Mobile",
    "router": "Router",
    "camera": "Camera",
    "generic": "Generic",
}
