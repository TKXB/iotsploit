"""Import an AUTOSAR ARXML description as a reviewable vehicle target.

``cantools`` is the source of truth for CAN frames and signals.  A small XML
pass supplies the vehicle facts it deliberately does not model: ECU instances,
communication clusters, connector membership, and Ethernet endpoints.  The
result uses the existing Target wire format and can be inspected before it is
loaded with ``target_import``.

This is intentionally not a general AUTOSAR object model.  LIN and Ethernet
are represented as topology only; CAN definitions are the only communication
payload converted into the target today.
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import cantools

MAX_ARXML_BYTES = 256 * 1024 * 1024
PARTIAL_SYSTEM_CATEGORY = "ECU_SYSTEM_DESCRIPTION"


class ArxmlImportError(ValueError):
    """An ARXML file cannot be safely or meaningfully imported."""


class _CantoolsDuplicateIndexFilter(logging.Filter):
    """Hide lossy convenience-index warnings; this importer keeps the list."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Overwriting message")


@dataclass(frozen=True)
class ArxmlImportResult:
    """The generated target plus concise information for a CLI summary."""

    target: Dict[str, Any]
    warnings: Tuple[str, ...]
    counts: Mapping[str, int]


def import_arxml(
    path: str | Path,
    *,
    target_id: str,
    name: str,
    source: Optional[str] = None,
    load_file: Optional[Callable[..., Any]] = None,
) -> ArxmlImportResult:
    """Build one vehicle target from ``path`` without changing backend state.

    Stable ids are derived from AUTOSAR short names, so running the import
    again produces diffable JSON.  ``source`` is provenance supplied by the
    caller; when absent only the filename is stored, never a machine-local
    absolute path.
    """
    arxml_path = Path(path)
    digest, size = _inspect_file(arxml_path)
    topology = _extract_topology(arxml_path)
    # The ElementTree for a production ARXML is hundreds of MiB.  Make sure it
    # is gone before cantools builds its own object graph for the same file.
    gc.collect()

    loader = load_file or cantools.database.load_file
    cantools_logger = logging.getLogger("cantools.database.can.database")
    duplicate_filter = _CantoolsDuplicateIndexFilter()
    cantools_logger.addFilter(duplicate_filter)
    try:
        database = loader(str(arxml_path), database_format="arxml", strict=True)
    except Exception as exc:
        raise ArxmlImportError(f"cantools could not parse {arxml_path.name}: {exc}") from exc
    finally:
        cantools_logger.removeFilter(duplicate_filter)

    warnings: List[str] = []
    category = topology.get("system_category")
    complete_vehicle = category != PARTIAL_SYSTEM_CATEGORY
    if not complete_vehicle:
        warnings.append(
            "SYSTEM category ECU_SYSTEM_DESCRIPTION is an ECU extract; the vehicle target is "
            "draft and must not be treated as a complete vehicle topology."
        )

    buses, buses_by_name = _build_buses(topology, database, warnings)
    components, connector_owners = _build_components(topology, buses, warnings)
    edges = _build_edges(buses, connector_owners)

    can_messages = 0
    can_signals = 0
    fd_messages = 0
    container_messages = 0
    wide_signals = 0
    message_names: Counter[str] = Counter()
    skipped_by_bus: Counter[str] = Counter()
    for message in getattr(database, "messages", ()) or ():
        bus_name = getattr(message, "bus_name", None)
        bus = buses_by_name.get(bus_name)
        if bus is None or bus.get("type") != "can":
            skipped_by_bus[str(bus_name)] += 1
            continue
        converted = _message_dict(message)
        bus["properties"].setdefault("messages", []).append(converted)
        can_messages += 1
        message_names[converted["name"]] += 1
        can_signals += len(converted["signals"])
        fd_messages += int(converted.get("is_fd") is True)
        container_messages += int(bool(converted.get("contained_messages")))
        wide_signals += sum(int(signal["length"] > 64) for signal in converted["signals"])

    if container_messages:
        warnings.append(
            f"{container_messages} CAN container frames were preserved with contained_messages; "
            "the current Flutter explorer does not expand their nested payloads."
        )
    if skipped_by_bus:
        summary = ", ".join(f"{bus}: {count}" for bus, count in sorted(skipped_by_bus.items()))
        warnings.append(f"CAN messages naming unknown buses were not imported ({summary}).")
    repeated_names = sum(count - 1 for count in message_names.values() if count > 1)
    if repeated_names:
        warnings.append(
            f"{repeated_names} CAN message occurrences reuse a name on another bus; every "
            "bus-specific occurrence was retained."
        )
    if wide_signals:
        warnings.append(
            f"{wide_signals} CAN signals wider than 64 bits were preserved without truncation; "
            "consumers must support wide raw values."
        )
    if any(bus["type"] in {"lin", "ethernet"} for bus in buses):
        warnings.append(
            "LIN and Ethernet clusters are imported as topology and endpoint metadata only; "
            "this importer converts communication payloads for CAN only."
        )

    counts = {
        "components": len(components),
        "buses": len(buses),
        "edges": len(edges),
        "can_messages": can_messages,
        "can_signals": can_signals,
        "can_fd_messages": fd_messages,
        "can_container_messages": container_messages,
    }
    metadata = {
        "source": source or arxml_path.name,
        "sha256": digest,
        "size_bytes": size,
        "schema": topology.get("schema"),
        "system_name": topology.get("system_name"),
        "system_category": category,
        "scope": "ecu_extract" if not complete_vehicle else "system_description",
        "complete_vehicle": complete_vehicle,
        "cantools_version": cantools.__version__,
        "counts": counts,
        "warnings": warnings,
    }
    target = {
        "target_id": target_id,
        "name": name,
        "type": "vehicle",
        "status": "active" if complete_vehicle else "draft",
        "properties": {"arxml_import": metadata},
        "components": components,
        "buses": buses,
        "edges": edges,
    }
    return ArxmlImportResult(target=target, warnings=tuple(warnings), counts=counts)


def _inspect_file(path: Path) -> Tuple[str, int]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ArxmlImportError(f"cannot read ARXML file {path}: {exc}") from exc
    if size > MAX_ARXML_BYTES:
        raise ArxmlImportError(
            f"ARXML file is {size} bytes; the import limit is {MAX_ARXML_BYTES} bytes"
        )

    digest = hashlib.sha256()
    markup_tail = b""
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                markup = (markup_tail + chunk).lower()
                if b"<!doctype" in markup or b"<!entity" in markup:
                    raise ArxmlImportError("ARXML files containing DTD or entity declarations are rejected")
                markup_tail = markup[-16:]
    except ArxmlImportError:
        raise
    except OSError as exc:
        raise ArxmlImportError(f"cannot read ARXML file {path}: {exc}") from exc
    return digest.hexdigest(), size


def _extract_topology(path: Path) -> Dict[str, Any]:
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        raise ArxmlImportError(f"invalid ARXML XML in {path.name}: {exc}") from exc

    root = tree.getroot()
    schema_location = next(
        (value for key, value in root.attrib.items() if _local(key) == "schemaLocation"), ""
    )
    schema = schema_location.split()[-1].rsplit("/", 1)[-1] if schema_location else None
    topology: Dict[str, Any] = {
        "schema": schema,
        "system_name": None,
        "system_category": None,
        "ecus": [],
        "networks": [],
    }

    for reference, element in _package_elements(root):
        kind = _local(element.tag)
        if kind == "SYSTEM" and topology["system_name"] is None:
            topology["system_name"] = _child_text(element, "SHORT-NAME")
            topology["system_category"] = _child_text(element, "CATEGORY")
        elif kind == "ECU-INSTANCE":
            topology["ecus"].append(_ecu_dict(reference, element))
        elif kind in {"CAN-CLUSTER", "LIN-CLUSTER", "ETHERNET-CLUSTER"}:
            topology["networks"].append(_network_dict(reference, element, kind))

    # Break the large reference cycle promptly; import_arxml invokes gc before
    # asking cantools to parse the file a second time.
    tree = None
    root = None
    return topology


def _package_elements(root: ET.Element) -> Iterable[Tuple[str, ET.Element]]:
    def walk(package: ET.Element, parent: str) -> Iterable[Tuple[str, ET.Element]]:
        package_name = _child_text(package, "SHORT-NAME")
        if not package_name:
            return
        package_ref = f"{parent}/{package_name}"
        elements = _child(package, "ELEMENTS")
        if elements is not None:
            for element in list(elements):
                short_name = _child_text(element, "SHORT-NAME")
                if short_name:
                    yield f"{package_ref}/{short_name}", element
        nested = _child(package, "AR-PACKAGES")
        if nested is not None:
            for child_package in _children(nested, "AR-PACKAGE"):
                yield from walk(child_package, package_ref)

    packages = _child(root, "AR-PACKAGES")
    if packages is None:
        return
    for package in _children(packages, "AR-PACKAGE"):
        yield from walk(package, "")


def _ecu_dict(reference: str, element: ET.Element) -> Dict[str, Any]:
    connectors = []
    connector_kinds = {
        "CAN-COMMUNICATION-CONNECTOR": "can",
        "LIN-COMMUNICATION-CONNECTOR": "lin",
        "ETHERNET-COMMUNICATION-CONNECTOR": "ethernet",
    }
    for connector in element.iter():
        connector_type = connector_kinds.get(_local(connector.tag))
        if connector_type is None:
            continue
        connector_name = _child_text(connector, "SHORT-NAME")
        if not connector_name:
            continue
        connectors.append(
            {
                "name": connector_name,
                "type": connector_type,
                "arxml_ref": f"{reference}/{connector_name}",
                "network_endpoint_refs": _descendant_texts(connector, "NETWORK-ENDPOINT-REF"),
            }
        )

    return {
        "name": _child_text(element, "SHORT-NAME") or reference.rsplit("/", 1)[-1],
        "arxml_ref": reference,
        "long_name": _element_text(_child(element, "LONG-NAME")),
        "description": _element_text(_child(element, "DESC")),
        "connectors": connectors,
    }


def _network_dict(reference: str, element: ET.Element, kind: str) -> Dict[str, Any]:
    network_type = kind.split("-", 1)[0].lower()
    channel_tag = {
        "can": "CAN-PHYSICAL-CHANNEL",
        "lin": "LIN-PHYSICAL-CHANNEL",
        "ethernet": "ETHERNET-PHYSICAL-CHANNEL",
    }[network_type]
    channels = [node for node in element.iter() if _local(node.tag) == channel_tag]
    connector_refs = _unique(
        text
        for channel in channels
        for text in _descendant_texts(channel, "COMMUNICATION-CONNECTOR-REF")
    )
    properties: Dict[str, Any] = {
        "arxml_ref": reference,
        "physical_channels": [
            name for channel in channels if (name := _child_text(channel, "SHORT-NAME"))
        ],
    }
    baudrate = _first_descendant_text(element, "BAUDRATE")
    if baudrate is not None:
        properties["baudrate"] = _integer(baudrate)

    if network_type == "lin":
        properties["frame_triggering_count"] = sum(
            1 for node in element.iter() if _local(node.tag) == "LIN-FRAME-TRIGGERING"
        )
    elif network_type == "ethernet":
        endpoints = []
        sockets = []
        for channel in channels:
            channel_name = _child_text(channel, "SHORT-NAME") or "channel"
            channel_ref = f"{reference}/{channel_name}"
            for endpoint in channel.iter():
                if _local(endpoint.tag) != "NETWORK-ENDPOINT":
                    continue
                endpoint_name = _child_text(endpoint, "SHORT-NAME")
                if not endpoint_name:
                    continue
                logical = _logical_address(endpoint)
                endpoint_row: Dict[str, Any] = {
                    "name": endpoint_name,
                    "arxml_ref": f"{channel_ref}/{endpoint_name}",
                    "addresses": _unique(
                        _descendant_texts(endpoint, "IPV-4-ADDRESS")
                        + _descendant_texts(endpoint, "IPV-6-ADDRESS")
                    ),
                }
                role = _first_descendant_text(endpoint, "DO-IP-ENTITY-ROLE")
                if role:
                    endpoint_row["doip_role"] = role
                if logical is not None:
                    endpoint_row["doip_logical_address"] = logical
                endpoints.append(endpoint_row)

            for socket in channel.iter():
                if _local(socket.tag) != "SOCKET-ADDRESS":
                    continue
                socket_name = _child_text(socket, "SHORT-NAME")
                if not socket_name:
                    continue
                protocol = None
                if any(_local(node.tag) == "TCP-TP" for node in socket.iter()):
                    protocol = "tcp"
                elif any(_local(node.tag) == "UDP-TP" for node in socket.iter()):
                    protocol = "udp"
                socket_row: Dict[str, Any] = {
                    "name": socket_name,
                    "arxml_ref": f"{channel_ref}/{socket_name}",
                    "protocol": protocol,
                    "network_endpoint_ref": _first_descendant_text(socket, "NETWORK-ENDPOINT-REF"),
                    "connector_ref": _first_descendant_text(socket, "CONNECTOR-REF"),
                }
                port = _first_descendant_text(socket, "PORT-NUMBER")
                if port is not None:
                    socket_row["port"] = _integer(port)
                sockets.append({key: value for key, value in socket_row.items() if value is not None})

        properties["network_endpoints"] = endpoints
        properties["sockets"] = sockets
        vlan = _first_descendant_text(element, "VLAN-IDENTIFIER")
        if vlan is not None:
            properties["vlan_id"] = _integer(vlan)

    return {
        "name": _child_text(element, "SHORT-NAME") or reference.rsplit("/", 1)[-1],
        "type": network_type,
        "arxml_ref": reference,
        "connector_refs": connector_refs,
        "properties": properties,
    }


def _build_buses(
    topology: Mapping[str, Any], database: Any, warnings: List[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    can_buses = {getattr(bus, "name", None): bus for bus in getattr(database, "buses", ()) or ()}
    buses = []
    by_name = {}
    for network in topology["networks"]:
        if network["name"] in by_name:
            raise ArxmlImportError(
                f"multiple communication clusters use short name {network['name']!r}; "
                "cantools cannot map their messages unambiguously"
            )
        properties = dict(network["properties"])
        can_bus = can_buses.get(network["name"])
        if network["type"] == "can" and can_bus is not None:
            baudrate = getattr(can_bus, "baudrate", None)
            fd_baudrate = getattr(can_bus, "fd_baudrate", None)
            if baudrate is not None:
                properties["baudrate"] = baudrate
            if fd_baudrate is not None:
                properties["fd_baudrate"] = fd_baudrate
        bus = {
            "bus_id": _stable_id("bus", network["type"], network["name"]),
            "name": network["name"],
            "type": network["type"],
            "properties": properties,
            "_connector_refs": network["connector_refs"],
        }
        buses.append(bus)
        by_name[network["name"]] = bus

    topology_names = {network["name"] for network in topology["networks"] if network["type"] == "can"}
    missing = sorted(name for name in can_buses if name and name not in topology_names)
    if missing:
        warnings.append(f"cantools exposed CAN buses absent from topology: {', '.join(missing)}")
    return buses, by_name


def _build_components(
    topology: Mapping[str, Any], buses: List[Dict[str, Any]], warnings: List[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    endpoints = {
        endpoint["arxml_ref"]: endpoint
        for bus in buses
        for endpoint in bus["properties"].get("network_endpoints", ())
    }
    sockets_by_connector: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for bus in buses:
        for socket in bus["properties"].get("sockets", ()):
            if connector_ref := socket.get("connector_ref"):
                sockets_by_connector[connector_ref].append(socket)

    components = []
    connector_owners = {}
    component_ids = set()
    for ecu in topology["ecus"]:
        component_id = _stable_id("c", ecu["name"])
        if component_id in component_ids:
            raise ArxmlImportError(
                f"multiple ECU instances map to component id {component_id!r}; "
                "their short names must be distinct"
            )
        component_ids.add(component_id)
        owned_endpoints = []
        owned_sockets = []
        for connector in ecu["connectors"]:
            connector_owners[connector["arxml_ref"]] = component_id
            owned_endpoints.extend(
                endpoints[reference]
                for reference in connector["network_endpoint_refs"]
                if reference in endpoints
            )
            owned_sockets.extend(sockets_by_connector.get(connector["arxml_ref"], ()))

        properties: Dict[str, Any] = {
            "arxml_ref": ecu["arxml_ref"],
            "connectors": ecu["connectors"],
        }
        if ecu["long_name"]:
            properties["long_name"] = ecu["long_name"]
        if ecu["description"]:
            properties["description"] = ecu["description"]
        if owned_endpoints:
            properties["network_endpoints"] = owned_endpoints
            addresses = [address for endpoint in owned_endpoints for address in endpoint["addresses"]]
            if addresses:
                properties["ip_address"] = addresses[0]
        if owned_sockets:
            properties["sockets"] = owned_sockets

        facets: Dict[str, Any] = {}
        logical_endpoints = [
            endpoint for endpoint in owned_endpoints if "doip_logical_address" in endpoint
        ]
        if logical_endpoints:
            endpoint = logical_endpoints[0]
            doip_sockets = [
                socket
                for socket in owned_sockets
                if socket.get("network_endpoint_ref") == endpoint["arxml_ref"]
            ]
            facet: Dict[str, Any] = {"logical_address": endpoint["doip_logical_address"]}
            if endpoint["addresses"]:
                facet["host"] = endpoint["addresses"][0]
            ports = [socket["port"] for socket in doip_sockets if "port" in socket]
            if ports:
                facet["port"] = ports[0]
            facets["doip"] = facet
        elif any(endpoint.get("doip_role") for endpoint in owned_endpoints):
            warnings.append(
                f"ECU {ecu['name']!r} has a DoIP endpoint but no logical address; no actionable "
                "doip facet was created."
            )

        components.append(
            {
                "component_id": component_id,
                "name": ecu["name"],
                "type": "ecu",
                "status": "active",
                "facets": facets,
                "properties": properties,
            }
        )
    return components, connector_owners


def _build_edges(
    buses: List[Dict[str, Any]], connector_owners: Mapping[str, str]
) -> List[Dict[str, Any]]:
    edges = []
    for bus in buses:
        by_owner: Dict[str, List[str]] = defaultdict(list)
        for connector_ref in bus.pop("_connector_refs", ()):
            owner = connector_owners.get(connector_ref)
            if owner is not None:
                by_owner[owner].append(connector_ref)
        for owner, connector_refs in by_owner.items():
            edges.append(
                {
                    "source": owner,
                    "target": bus["bus_id"],
                    "relation": "bus_member",
                    "properties": {"source": "arxml", "connector_refs": connector_refs},
                }
            )
    return edges


def _message_dict(message: Any, *, nested: bool = False) -> Dict[str, Any]:
    converted: Dict[str, Any] = {
        "frame_id": getattr(message, "frame_id", 0),
        "name": getattr(message, "name", ""),
        "dlc": getattr(message, "length", 0),
        "is_extended": bool(getattr(message, "is_extended_frame", False)),
        "is_fd": bool(getattr(message, "is_fd", False)),
        "signals": [_signal_dict(signal) for signal in getattr(message, "signals", ()) or ()],
    }
    optional = {
        "cycle_time_ms": getattr(message, "cycle_time", None),
        "senders": list(getattr(message, "senders", ()) or ()),
        "header_id": getattr(message, "header_id", None),
    }
    converted.update({key: value for key, value in optional.items() if value not in (None, [])})
    contained = getattr(message, "contained_messages", ()) or ()
    if contained:
        converted["contained_messages"] = [
            _message_dict(child, nested=True) for child in contained if child is not message
        ]
    if nested:
        # A contained PDU's frame id is not its identity; AUTOSAR uses the
        # header id.  Keep the value when cantools has one, but do not invent it.
        converted.pop("is_extended", None)
    return _json_value(converted)


def _signal_dict(signal: Any) -> Dict[str, Any]:
    conversion = getattr(signal, "conversion", None)
    scale = getattr(conversion, "scale", getattr(signal, "scale", 1.0))
    offset = getattr(conversion, "offset", getattr(signal, "offset", 0.0))
    choices = getattr(conversion, "choices", getattr(signal, "choices", None))
    multiplexer = None
    if getattr(signal, "is_multiplexer", False):
        multiplexer = "M"
    elif getattr(signal, "multiplexer_ids", None):
        multiplexer = ",".join(f"m{value}" for value in signal.multiplexer_ids)

    converted: Dict[str, Any] = {
        "name": getattr(signal, "name", ""),
        "start_bit": getattr(signal, "start", 0),
        "length": getattr(signal, "length", 0),
        "byte_order": "little" if getattr(signal, "byte_order", "little_endian") == "little_endian" else "big",
        "signed": bool(getattr(signal, "is_signed", False)),
        "factor": scale,
        "offset": offset,
        "minimum": getattr(signal, "minimum", None),
        "maximum": getattr(signal, "maximum", None),
        "unit": getattr(signal, "unit", None) or "",
        "multiplexer": multiplexer,
        # An IEEE-754 payload is not a scaled integer, and factor/offset do not
        # say so. An encoder rebuilding this signal without the flag packs a
        # float as an integer and is wrong by the whole width of the field.
        "is_float": bool(getattr(signal, "is_float", False)),
    }
    receivers = list(getattr(signal, "receivers", ()) or ())
    if receivers:
        converted["receivers"] = receivers
    if choices:
        converted["choices"] = choices
    multiplexer_signal = getattr(signal, "multiplexer_signal", None)
    if multiplexer_signal:
        converted["multiplexer_signal"] = multiplexer_signal
    return _json_value(converted)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # cantools uses NamedSignalValue for textual choice labels.
    return str(value)


def _stable_id(prefix: str, *parts: str) -> str:
    slug = "_".join(parts).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    return f"{prefix}_{slug or 'unnamed'}"


def _logical_address(element: ET.Element) -> Optional[int]:
    for node in element.iter():
        if _local(node.tag) not in {"DO-IP-LOGICAL-ADDRESS", "LOGICAL-ADDRESS"}:
            continue
        text = (node.text or "").strip()
        if not text:
            continue
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(text, 16)
            except ValueError:
                return None
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> Optional[ET.Element]:
    return next((child for child in list(element) if _local(child.tag) == name), None)


def _children(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (child for child in list(element) if _local(child.tag) == name)


def _child_text(element: ET.Element, name: str) -> Optional[str]:
    child = _child(element, name)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _first_descendant_text(element: ET.Element, name: str) -> Optional[str]:
    for child in element.iter():
        if _local(child.tag) == name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _descendant_texts(element: ET.Element, name: str) -> List[str]:
    return [
        child.text.strip()
        for child in element.iter()
        if _local(child.tag) == name and child.text and child.text.strip()
    ]


def _element_text(element: Optional[ET.Element]) -> Optional[str]:
    if element is None:
        return None
    text = "\n".join(part.strip() for part in element.itertext() if part.strip())
    return text or None


def _integer(value: str) -> int | str:
    try:
        return int(value, 0)
    except ValueError:
        return value


def _unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(values))


def dump_target(result: ArxmlImportResult, output: str | Path) -> None:
    """Write a result in the existing ``target_import`` envelope."""
    try:
        with Path(output).open("w", encoding="utf-8") as handle:
            json.dump({"targets": [result.target]}, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except OSError as exc:
        raise ArxmlImportError(f"cannot write target JSON {output}: {exc}") from exc
