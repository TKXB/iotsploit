"""Pure-Python read-time reconciliation of observations against a target model.

Keeps stored provenance (`component_id`, `scope_key`) untouched while deriving:
- `bus_id`: configured target bus behind a scan's `scope_key`, if resolvable
- `host_key`: IPv4 host grouping hint for IP/port/service discoveries
- `resolved_component_id` + `attribution` (`declared` | `inferred` | `unclaimed`)
- `documentation` (`documented` | `undocumented` | `unchecked`)

This module must stay free of persistence and Django imports.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from iotsploit_core.domain.observation import SUBJECT_SELF, ObservationRecord, ScanSummary

_IPV4_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_PORT_SUFFIX_RE = re.compile(r":(\d{1,5})(?:/(?:tcp|udp))?$")
_NETWORK_PROTOCOLS = frozenset({"ip", "tcp", "udp", "doip", "someip", "ethernet", "ssh", "http", "https"})


def canonical_can_frame_id(frame_id: int, is_extended: bool = False) -> str:
    """Match `can_facet.py` / Flutter `canonicalFrameId` formatting."""
    return f"{int(frame_id):X}".zfill(8 if is_extended else 3)


def extract_host_ip(protocol: str, subject_id: Optional[str], value: Any) -> Optional[str]:
    """Extract a canonical IPv4 host key when an observation names an IP host."""
    if protocol not in _NETWORK_PROTOCOLS:
        return None
    if subject_id:
        match = _IPV4_RE.search(subject_id)
        if match and _is_valid_ipv4(match.group(1)):
            return match.group(1)
    if isinstance(value, Mapping):
        ip_val = value.get("ip")
        if isinstance(ip_val, str) and _is_valid_ipv4(ip_val.strip()):
            return ip_val.strip()
        endpoints = value.get("endpoints")
        if isinstance(endpoints, list):
            for ep in endpoints:
                if isinstance(ep, Mapping) and isinstance(ep.get("ip"), str):
                    candidate = ep["ip"].strip()
                    if _is_valid_ipv4(candidate):
                        return candidate
    return None


def _is_valid_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def _extract_port(subject_id: Optional[str]) -> Optional[int]:
    if not subject_id:
        return None
    if subject_id.isdigit():
        port = int(subject_id)
        return port if 0 < port <= 65535 else None
    match = _PORT_SUFFIX_RE.search(subject_id.strip())
    if match:
        port = int(match.group(1))
        return port if 0 < port <= 65535 else None
    return None


@dataclass(frozen=True)
class ReconciledObservation:
    """Read-time enrichment for one ObservationRecord."""

    record: ObservationRecord
    resolved_component_id: Optional[str]
    attribution: str  # "declared" | "inferred" | "unclaimed"
    documentation: str  # "documented" | "undocumented" | "unchecked"
    bus_id: Optional[str]
    host_key: Optional[str]


class _TargetFacetIndex:
    """Pre-indexed target topology and facet lookup tables for O(1) reconciliation."""

    def __init__(self, target: Optional[Mapping[str, Any]]) -> None:
        self.bus_ids: set[str] = set()
        self.bus_networks: list[tuple[str, ipaddress.IPv4Network]] = []
        self.bus_frames: dict[str, set[str]] = {}
        self.all_bus_frames: set[str] = set()
        self.component_ids: set[str] = set()
        self.component_buses: dict[str, set[str]] = {}
        self.component_can_frames: dict[str, set[str]] = {}
        self.can_senders_by_bus: dict[tuple[str, str], set[str]] = {}
        self.can_senders_any: dict[str, set[str]] = {}
        self.components_by_ip: dict[str, set[str]] = {}
        self.component_ports: dict[str, set[int]] = {}
        self.component_doip: dict[str, tuple[Optional[str], Optional[int]]] = {}

        if not isinstance(target, Mapping):
            return

        for bus in target.get("buses") or []:
            if not isinstance(bus, Mapping):
                continue
            bus_id = bus.get("bus_id")
            if not isinstance(bus_id, str) or not bus_id:
                continue
            self.bus_ids.add(bus_id)
            props = bus.get("properties")
            if isinstance(props, Mapping):
                for cidr_key in ("cidr", "subnet", "network"):
                    raw_cidr = props.get(cidr_key)
                    if isinstance(raw_cidr, str):
                        try:
                            net = ipaddress.IPv4Network(raw_cidr.strip(), strict=False)
                            self.bus_networks.append((bus_id, net))
                        except ValueError:
                            pass
                frames: set[str] = set()
                for msg in props.get("messages") or []:
                    if isinstance(msg, Mapping) and isinstance(msg.get("frame_id"), (int, float)):
                        hex_id = canonical_can_frame_id(
                            int(msg["frame_id"]),
                            is_extended=bool(msg.get("is_extended")),
                        )
                        frames.add(hex_id)
                        self.all_bus_frames.add(hex_id)
                if frames:
                    self.bus_frames[bus_id] = frames

        for edge in target.get("edges") or []:
            if not isinstance(edge, Mapping):
                continue
            src = edge.get("source")
            dst = edge.get("target")
            if isinstance(src, str) and isinstance(dst, str) and dst in self.bus_ids:
                self.component_buses.setdefault(src, set()).add(dst)

        for comp in target.get("components") or []:
            if not isinstance(comp, Mapping):
                continue
            comp_id = comp.get("component_id")
            if not isinstance(comp_id, str) or not comp_id:
                continue
            self.component_ids.add(comp_id)
            facets = comp.get("facets")
            if not isinstance(facets, Mapping):
                continue

            # CAN facet
            can_facet = facets.get("can")
            if isinstance(can_facet, Mapping):
                facet_bus = can_facet.get("bus_id") if isinstance(can_facet.get("bus_id"), str) else None
                comp_frames: set[str] = set()
                for msg in can_facet.get("messages") or []:
                    if isinstance(msg, Mapping) and isinstance(msg.get("frame_id"), (int, float)):
                        hex_id = canonical_can_frame_id(
                            int(msg["frame_id"]),
                            is_extended=bool(msg.get("is_extended")),
                        )
                        comp_frames.add(hex_id)
                        self.can_senders_any.setdefault(hex_id, set()).add(comp_id)
                        if facet_bus:
                            self.can_senders_by_bus.setdefault((facet_bus, hex_id), set()).add(comp_id)
                        for b in self.component_buses.get(comp_id, ()):
                            self.can_senders_by_bus.setdefault((b, hex_id), set()).add(comp_id)
                if comp_frames:
                    self.component_can_frames[comp_id] = comp_frames

            # DoIP facet
            doip_facet = facets.get("doip")
            if isinstance(doip_facet, Mapping):
                host = doip_facet.get("host")
                port = doip_facet.get("port")
                host_str = host.strip() if isinstance(host, str) and _is_valid_ipv4(host.strip()) else None
                port_int = int(port) if isinstance(port, (int, float)) else None
                self.component_doip[comp_id] = (host_str, port_int)
                if host_str:
                    self.components_by_ip.setdefault(host_str, set()).add(comp_id)
                if port_int:
                    self.component_ports.setdefault(comp_id, set()).add(port_int)

            # Generic IP/port facets (ethernet, ssh, etc.)
            for facet_val in facets.values():
                if not isinstance(facet_val, Mapping):
                    continue
                for ip_key in ("host", "ip", "ip_address"):
                    val = facet_val.get(ip_key)
                    if isinstance(val, str) and _is_valid_ipv4(val.strip()):
                        self.components_by_ip.setdefault(val.strip(), set()).add(comp_id)
                port_val = facet_val.get("port")
                if isinstance(port_val, (int, float)) and 0 < int(port_val) <= 65535:
                    self.component_ports.setdefault(comp_id, set()).add(int(port_val))
                interfaces = facet_val.get("interfaces")
                if isinstance(interfaces, list):
                    for iface in interfaces:
                        if not isinstance(iface, Mapping):
                            continue
                        for ip_key in ("ip", "ip_address", "address"):
                            val = iface.get(ip_key)
                            if isinstance(val, str):
                                raw_ip = val.split("/")[0].strip()
                                if _is_valid_ipv4(raw_ip):
                                    self.components_by_ip.setdefault(raw_ip, set()).add(comp_id)

    def resolve_bus_id(self, scope_key: str) -> Optional[str]:
        if not scope_key or not self.bus_ids:
            return None
        if scope_key in self.bus_ids:
            return scope_key
        # Match colon-delimited tokens (e.g. `can:b_can`, `uds:can:b_can:0x7E0`)
        for token in scope_key.split(":"):
            if token in self.bus_ids:
                return token
        # Match CIDR in `lan:192.168.10.0/24:...` against configured bus subnets
        if self.bus_networks:
            for token in scope_key.split(":"):
                if "/" in token:
                    try:
                        net = ipaddress.IPv4Network(token.strip(), strict=False)
                    except ValueError:
                        continue
                    for bus_id, bus_net in self.bus_networks:
                        if net.subnet_of(bus_net) or bus_net.subnet_of(net):
                            return bus_id
        return None


def resolve_scan_bus_id(target: Optional[Mapping[str, Any]], scope_key: str) -> Optional[str]:
    """Resolve the configured target `bus_id` for a single `scope_key`."""
    return _TargetFacetIndex(target).resolve_bus_id(scope_key)


def reconcile_observations(
    target: Optional[Mapping[str, Any]],
    records: Sequence[ObservationRecord],
    scans: Sequence[ScanSummary] = (),
) -> tuple[list[ReconciledObservation], list[dict[str, Any]]]:
    """Reconcile observation records and scan summaries against [target]."""
    index = _TargetFacetIndex(target)
    reconciled: list[ReconciledObservation] = []

    for record in records:
        protocol = (record.protocol or "").strip().lower()
        subject_kind = (record.subject_kind or "").strip()
        subject_id = (record.subject_id or "").strip()
        bus_id = index.resolve_bus_id(record.scope_key)
        host_key = extract_host_ip(protocol, subject_id, record.value)

        # 1. Attribution
        if record.component_id:
            resolved_component_id: Optional[str] = record.component_id
            attribution = "declared"
        else:
            resolved_component_id = _infer_component(
                index,
                protocol=protocol,
                subject_kind=subject_kind,
                subject_id=subject_id,
                bus_id=bus_id,
                host_key=host_key,
            )
            attribution = "inferred" if resolved_component_id is not None else "unclaimed"

        # 2. Documentation
        documentation = _classify_documentation(
            index,
            protocol=protocol,
            subject_kind=subject_kind,
            subject_id=subject_id,
            bus_id=bus_id,
            host_key=host_key,
            resolved_component_id=resolved_component_id,
        )

        reconciled.append(
            ReconciledObservation(
                record=record,
                resolved_component_id=resolved_component_id,
                attribution=attribution,
                documentation=documentation,
                bus_id=bus_id,
                host_key=host_key,
            )
        )

    serialized_scans = [
        {
            "scan_id": scan.scan_id,
            "source": scan.source,
            "scope_key": scan.scope_key,
            "component_id": scan.component_id,
            "bus_id": index.resolve_bus_id(scan.scope_key),
            "is_complete": scan.is_complete,
            "facts_count": scan.facts_count,
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        }
        for scan in scans
    ]
    return reconciled, serialized_scans


def _infer_component(
    index: _TargetFacetIndex,
    *,
    protocol: str,
    subject_kind: str,
    subject_id: str,
    bus_id: Optional[str],
    host_key: Optional[str],
) -> Optional[str]:
    if subject_kind == SUBJECT_SELF or not subject_id:
        return None
    if protocol == "can" and subject_kind == "message":
        senders = (
            index.can_senders_by_bus.get((bus_id, subject_id))
            if bus_id
            else index.can_senders_any.get(subject_id)
        )
        if senders and len(senders) == 1:
            return next(iter(senders))
        return None
    if host_key:
        matches = index.components_by_ip.get(host_key)
        if matches and len(matches) == 1:
            return next(iter(matches))
    return None


def _classify_documentation(
    index: _TargetFacetIndex,
    *,
    protocol: str,
    subject_kind: str,
    subject_id: str,
    bus_id: Optional[str],
    host_key: Optional[str],
    resolved_component_id: Optional[str],
) -> str:
    if subject_kind == SUBJECT_SELF or not subject_id:
        return "unchecked"

    if protocol == "can" and subject_kind == "message":
        on_component = (
            resolved_component_id is not None
            and subject_id in index.component_can_frames.get(resolved_component_id, ())
        )
        on_bus = (
            bus_id is not None and subject_id in index.bus_frames.get(bus_id, ())
        ) or (bus_id is None and subject_id in index.all_bus_frames)
        return "documented" if (on_component or on_bus) else "undocumented"

    if protocol == "doip" and subject_kind == "endpoint" and resolved_component_id in index.component_doip:
        cfg_host, cfg_port = index.component_doip[resolved_component_id]
        obs_port = _extract_port(subject_id)
        host_ok = cfg_host is None or host_key == cfg_host
        port_ok = cfg_port is None or obs_port is None or obs_port == cfg_port
        return "documented" if (host_ok and port_ok) else "undocumented"

    if protocol in ("tcp", "udp") and subject_kind == "port" and resolved_component_id:
        obs_port = _extract_port(subject_id)
        if obs_port is not None and obs_port in index.component_ports.get(resolved_component_id, ()):
            return "documented"

    return "unchecked"
