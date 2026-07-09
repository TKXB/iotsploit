from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field


class Target(BaseModel, ABC):
    target_id: str
    name: str
    type: str
    status: str = "active"
    properties: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    location: Optional[str] = None
    components: List["Component"] = Field(default_factory=list)
    interfaces: List["Interface"] = Field(default_factory=list)

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        raise NotImplementedError

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

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update(
            {
                "adb_serial_id": self.adb_serial_id,
                "usb_vendor_id": self.usb_vendor_id,
                "usb_product_id": self.usb_product_id,
            }
        )
        return info


class CameraComponent(Component):
    resolution: Optional[str] = None
    fps: Optional[int] = None
    codec: Optional[str] = None
    rtsp_url: Optional[str] = None

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({"resolution": self.resolution, "fps": self.fps, "codec": self.codec, "rtsp_url": self.rtsp_url})
        return info


class SensorComponent(Component):
    sensor_type: Optional[str] = None
    unit: Optional[str] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    accuracy: Optional[float] = None

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update(
            {
                "sensor_type": self.sensor_type,
                "unit": self.unit,
                "range_min": self.range_min,
                "range_max": self.range_max,
                "accuracy": self.accuracy,
            }
        )
        return info


class NetworkComponent(Component):
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    interface_type: Optional[str] = None
    bandwidth: Optional[str] = None

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update(
            {
                "ip_address": self.ip_address,
                "mac_address": self.mac_address,
                "interface_type": self.interface_type,
                "bandwidth": self.bandwidth,
            }
        )
        return info


class ECUComponent(Component):
    ecu_type: Optional[str] = None
    protocol: Optional[str] = None
    address: Optional[str] = None
    firmware_version: Optional[str] = None

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update(
            {"ecu_type": self.ecu_type, "protocol": self.protocol, "address": self.address, "firmware_version": self.firmware_version}
        )
        return info


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

    def get_info(self) -> Dict[str, Any]:
        info = super().model_dump()
        info.update(
            {
                "ip_address": self.ip_address,
                "location": self.location,
                "components": [comp.model_dump() for comp in self.components],
                "interfaces": [intf.model_dump() for intf in self.interfaces],
            }
        )
        return info

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

    def get_info(self) -> Dict[str, Any]:
        info = self.model_dump()
        # Ensure components and interfaces are serialized properly
        info.update(
            {
                "components": [comp.model_dump() for comp in self.components],
                "interfaces": [intf.model_dump() for intf in self.interfaces],
            }
        )
        return info


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


