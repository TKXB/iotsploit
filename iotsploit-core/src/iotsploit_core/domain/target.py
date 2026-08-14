from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field, SerializeAsAny, field_validator, model_validator

from iotsploit_core.domain.facet import Facet, resolve_facets

#: Where interfaces used to live on a stored target. Read, never written.
LEGACY_INTERFACES_KEY = "interfaces"


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
    # An ethernet port and an ECU are both endpoints: same id, name, type,
    # status, and both carry protocol config. They were two lists until the
    # split started doing harm -- an interface could not hold a facet, so the
    # host and port of the protocol it carries had to be stored on some
    # component instead. ``type`` says which kind a row is.
    components: SerializeAsAny[List["Component"]] = Field(default_factory=list)
    # Plane T. The graph is projected from these on demand, never stored as one.
    buses: List["Bus"] = Field(default_factory=list)
    edges: List["Edge"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_edge_endpoints(self) -> "Target":
        """Every edge endpoint must resolve to something on this target.

        An edge to a deleted component is not a harmless leftover: it is a
        topology claim that reads as true and answers reachability questions
        wrongly. Better to reject the write than to store a lie.
        """
        if not self.edges:
            return self
        known = {self.target_id}
        known.update(comp.component_id for comp in self.components)
        known.update(bus.bus_id for bus in self.buses)
        for edge in self.edges:
            for role, endpoint in (("source", edge.source), ("target", edge.target)):
                if endpoint not in known:
                    raise ValueError(
                        f"edge {edge.relation!r} has unknown {role} {endpoint!r}; "
                        f"known ids: {sorted(known)}"
                    )
        return self

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
    # Typed, protocol-specific configuration, keyed by facet name. Open by
    # design: core registers none of these, plugins register their own.
    facets: SerializeAsAny[Dict[str, Facet]] = Field(default_factory=dict)
    # Unstructured leftovers only. Anything a driver acts on belongs in a facet.
    properties: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("facets", mode="before")
    @classmethod
    def _resolve_facets(cls, value: Any) -> Any:
        return resolve_facets(value)

    def facet(self, key: str) -> Optional[Facet]:
        """The facet stored under ``key``, or None. Never raises."""
        return self.facets.get(key)

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


def fold_legacy_interfaces(data: Dict[str, Any]) -> Dict[str, Any]:
    """Move a stored target's ``interfaces`` into its ``components``.

    Interfaces were a parallel list with a component's shape minus facets.
    Nothing ever branched on which list a row was in; the one real difference
    was that an interface could not carry protocol config.

    Ids were already unique across both lists -- edge validation pooled them
    into one namespace -- so an interface keeps its id and every edge goes on
    pointing at the same thing. Folding twice is a no-op, which is what makes
    this safe to run on every read.

    Returns a new dict; the argument is left alone.
    """
    if LEGACY_INTERFACES_KEY not in data:
        return data

    legacy = data.get(LEGACY_INTERFACES_KEY) or []
    folded = dict(data)
    components = list(folded.get("components") or [])
    taken = {c.get("component_id") for c in components if isinstance(c, dict)}

    for raw in legacy:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["component_id"] = item.pop("interface_id", None) or item.get("component_id") or ""
        if item["component_id"] in taken:
            continue
        item.setdefault("type", "interface")
        components.append(item)
        taken.add(item["component_id"])

    folded["components"] = components
    folded.pop(LEGACY_INTERFACES_KEY, None)
    return folded


class Bus(BaseModel):
    """A shared medium: a CAN bus, an Ethernet segment, a VLAN.

    A bus is a *scope*, not an endpoint -- you do not query it by id, things
    live on it. CAN messages anchor here rather than to a component, because a
    frame has one sender and many receivers. Catalog rows need a stable bus id
    to point at, which is why this exists before any DBC import.
    """

    bus_id: str
    name: str
    type: str  # "can" | "ethernet" | "vlan"
    properties: Dict[str, Any] = Field(default_factory=dict)

    def get_info(self) -> Dict[str, Any]:
        return self.model_dump()


class Edge(BaseModel):
    """A typed relationship between two things on a target.

    Endpoints are ids of a component, interface, bus, or the target itself.
    """

    source: str
    target: str
    relation: str  # "connects" | "hosts" | "bus_member" | "reachable_from"
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
