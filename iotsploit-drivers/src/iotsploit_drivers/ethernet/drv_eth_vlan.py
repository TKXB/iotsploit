from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from typing import Any, Optional

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_priv import PrivilegedHelperError, call as privileged_call


IP = "/usr/sbin/ip"
NMCLI = "/usr/bin/nmcli"
PROFILE_PREFIX = "iotsploit-vlan-"
MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


def _run(argv: list[str]) -> str:
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={"LC_ALL": "C"},
        close_fds=True,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"{argv[0]} failed")
    return result.stdout


def _connection_rows() -> list[dict[str, str]]:
    output = _run([
        NMCLI,
        "--terse",
        "--escape",
        "no",
        "--fields",
        "NAME,UUID,TYPE,DEVICE",
        "connection",
        "show",
    ])
    rows = []
    for line in output.splitlines():
        fields = line.split(":", 3)
        if len(fields) == 4:
            rows.append(dict(zip(("name", "uuid", "type", "device"), fields)))
    return rows


def _connection_values(uuid: str) -> list[str]:
    output = _run([
        NMCLI,
        "--get-values",
        "vlan.parent,vlan.id,ipv4.addresses,802-3-ethernet.cloned-mac-address,connection.autoconnect",
        "connection",
        "show",
        "uuid",
        uuid,
    ])
    values = output.splitlines()
    return (values + [""] * 5)[:5]


def _permanent_neighbor(interface: str) -> dict[str, str] | None:
    if not interface:
        return None
    try:
        rows = json.loads(_run([IP, "-json", "neigh", "show", "dev", interface, "nud", "permanent"]))
    except (RuntimeError, json.JSONDecodeError):
        return None
    for row in rows:
        if row.get("dst") and row.get("lladdr"):
            return {"ip": row["dst"], "mac": row["lladdr"].lower()}
    return None


def _interface_addresses(interface: str) -> set[str]:
    try:
        rows = json.loads(_run([IP, "-json", "address", "show", "dev", interface]))
    except (RuntimeError, json.JSONDecodeError):
        return set()
    return {
        item["local"]
        for row in rows
        for item in row.get("addr_info", [])
        if item.get("family") == "inet" and item.get("local")
    }


def _vlan_profiles() -> list[dict[str, Any]]:
    profiles = []
    for row in _connection_rows():
        if row["type"] != "vlan":
            continue
        parent, vlan_id, address, local_mac, autoconnect = _connection_values(row["uuid"])
        try:
            parsed_vlan_id = int(vlan_id)
        except ValueError:
            continue
        expected_name = f"{PROFILE_PREFIX}{parent}-{parsed_vlan_id}"
        profiles.append({
            "profile": row["name"],
            "uuid": row["uuid"],
            "parent": parent,
            "vlan_id": parsed_vlan_id,
            "interface": row["device"] or f"{parent}.{parsed_vlan_id}",
            "active": bool(row["device"]),
            "address": address,
            "local_mac": "" if local_mac == "--" else local_mac.lower(),
            "autoconnect": autoconnect == "yes",
            "managed": row["name"] == expected_name,
            "peer": _permanent_neighbor(row["device"]),
        })
    return profiles


def _ethernet_devices() -> list[dict[str, str]]:
    """Ethernet parents NetworkManager is willing to build a VLAN on.

    A container or hypervisor host reports its veth and vmnet endpoints as
    ethernet too -- 24 of 25 rows on a developer box with Docker running. NM
    leaves those unmanaged, and a VLAN profile on an unmanaged parent never
    activates, so they are not slow or noisy candidates: they are not
    candidates.
    """
    output = _run([
        NMCLI,
        "--terse",
        "--escape",
        "no",
        "--fields",
        "DEVICE,TYPE,STATE,CONNECTION",
        "device",
        "status",
    ])
    devices = []
    for line in output.splitlines():
        fields = line.split(":", 3)
        if len(fields) == 4 and fields[1] == "ethernet" and fields[2] != "unmanaged":
            devices.append(dict(zip(("interface", "type", "state", "connection"), fields)))
    return devices


# Declared for the operator-facing form; `_config` re-validates every value,
# because a schema describes a field and cannot know that a peer which answers
# no ARP needs both peer_ip and peer_mac, or that an address already on the
# parent cannot move to a VLAN.
_VLAN_PARAMETERS = {
    "vlan_id": {
        "type": "int",
        "required": True,
        "description": "VLAN tag, 1-4094",
        "validation": {"min": 1, "max": 4094},
    },
    "address": {
        "type": "str",
        "required": True,
        "description": "Local IPv4 address in CIDR notation, e.g. 172.31.67.6/16",
    },
    "local_mac": {
        "type": "str",
        "required": False,
        "description": "Cloned MAC for the VLAN interface; leave empty to keep the parent's",
    },
    "peer_ip": {
        "type": "str",
        "required": False,
        "description": "Peer IPv4 for a permanent neighbour entry; set with peer_mac or not at all",
    },
    "peer_mac": {
        "type": "str",
        "required": False,
        "description": "Peer MAC for the permanent neighbour entry",
    },
}


class EthernetVlanDriver(BaseDeviceDriver):
    REQUIRES = ("platform:linux", "binary:nmcli", "privileged-helper")

    def __init__(self):
        super().__init__({
            "Name": "Ethernet VLAN",
            "Description": "Manage persistent NetworkManager VLAN profiles",
        })
        self.supported_commands = {
            "add_vlan": {
                "description": "Add and activate a persistent VLAN profile",
                "parameters": _VLAN_PARAMETERS,
            },
            "edit_vlan": {
                "description": "Edit and reactivate an IoTSploit VLAN profile",
                "parameters": _VLAN_PARAMETERS,
            },
            "delete_vlan": {
                "description": "Delete an IoTSploit VLAN profile",
                "parameters": {"vlan_id": _VLAN_PARAMETERS["vlan_id"]},
            },
            "vlan_status": "Display VLAN profiles and live state",
        }

    def _scan_impl(self) -> list[Device]:
        profiles = _vlan_profiles()
        return [
            Device(
                device_id=f"eth_vlan_{item['interface']}",
                name=f"Ethernet VLANs ({item['interface']})",
                device_type=DeviceType.Ethernet,
                attributes={
                    **item,
                    "vlans": sorted(
                        (profile for profile in profiles if profile["parent"] == item["interface"]),
                        key=lambda profile: profile["vlan_id"],
                    ),
                },
            )
            for item in _ethernet_devices()
        ]

    @staticmethod
    def _parent(device: Device) -> str:
        parent = str(device.attributes.get("interface") or "")
        if not re.fullmatch(r"[a-z0-9._-]{1,15}", parent):
            raise ValueError("Selected device has no valid Ethernet interface")
        return parent

    def _initialize_impl(self, device: Device) -> bool:
        self._parent(device)
        return True

    def _connect_impl(self, device: Device) -> bool:
        self._parent(device)
        return True

    @staticmethod
    def _vlan_id(args: dict[str, Any]) -> int:
        value = args.get("vlan_id")
        if type(value) is not int or not 1 <= value <= 4_094:
            raise ValueError("vlan_id must be an integer from 1 to 4094")
        return value

    @staticmethod
    def _mac(value: Any, name: str) -> str | None:
        if value in (None, ""):
            return None
        address = str(value).lower()
        if not MAC.fullmatch(address):
            raise ValueError(f"{name} must be a colon-separated MAC address")
        octets = bytes.fromhex(address.replace(":", ""))
        if octets == b"\x00" * 6 or octets == b"\xff" * 6 or octets[0] & 1:
            raise ValueError(f"{name} must be a unicast MAC address")
        return address

    def _config(self, device: Device, args: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(args, dict):
            raise ValueError("VLAN command arguments must be an object")
        address_text = str(args.get("address") or "")
        if "/" not in address_text:
            raise ValueError("address must be an IPv4 interface in CIDR notation")
        try:
            address = ipaddress.ip_interface(address_text)
        except ValueError as exc:
            raise ValueError("address must be an IPv4 interface in CIDR notation") from exc
        if address.version != 4 or address.ip.is_unspecified or address.ip.is_multicast:
            raise ValueError("address must be a usable IPv4 interface in CIDR notation")
        peer_ip = args.get("peer_ip") or None
        if peer_ip is not None:
            try:
                parsed_peer = ipaddress.ip_address(str(peer_ip))
            except ValueError as exc:
                raise ValueError("peer_ip must be an IPv4 address") from exc
            if parsed_peer.version != 4 or parsed_peer.is_unspecified or parsed_peer.is_multicast:
                raise ValueError("peer_ip must be a usable IPv4 address")
            peer_ip = str(parsed_peer)
        peer_mac = self._mac(args.get("peer_mac"), "peer_mac")
        if (peer_ip is None) != (peer_mac is None):
            raise ValueError("peer_ip and peer_mac must both be set or both be empty")
        return {
            "parent": self._parent(device),
            "vlan_id": self._vlan_id(args),
            "address": str(address),
            "local_mac": self._mac(args.get("local_mac"), "local_mac"),
            "peer_ip": peer_ip,
            "peer_mac": peer_mac,
        }

    @staticmethod
    def _owned_profile(parent: str, vlan_id: int) -> dict[str, Any] | None:
        return next(
            (
                profile
                for profile in _vlan_profiles()
                if profile["parent"] == parent and profile["vlan_id"] == vlan_id and profile["managed"]
            ),
            None,
        )

    @staticmethod
    def _profile_exists(parent: str, vlan_id: int) -> bool:
        return any(
            profile["parent"] == parent and profile["vlan_id"] == vlan_id
            for profile in _vlan_profiles()
        )

    @staticmethod
    def _run_privileged(verb: str, args: dict[str, Any]) -> str:
        try:
            result = privileged_call(verb, args)
        except PrivilegedHelperError as exc:
            raise RuntimeError(str(exc)) from exc
        if not result.ok:
            raise RuntimeError(result.stderr or f"{verb} failed with exit {result.exit}")
        return result.stdout.strip()

    def _command_impl(self, device: Device, command: str, args: Optional[dict] = None) -> str:
        parent = self._parent(device)
        if command == "vlan_status":
            profiles = [profile for profile in _vlan_profiles() if profile["parent"] == parent]
            return json.dumps({"parent": parent, "vlans": profiles}, indent=2, sort_keys=True)
        if command == "delete_vlan":
            if not isinstance(args, dict):
                raise ValueError("VLAN command arguments must be an object")
            vlan_id = self._vlan_id(args)
            if self._owned_profile(parent, vlan_id) is None:
                raise ValueError(f"VLAN {parent}.{vlan_id} is not managed by IoTSploit")
            self._run_privileged("vlan-delete", {"parent": parent, "vlan_id": vlan_id})
            return f"Deleted VLAN {parent}.{vlan_id}"
        if command not in {"add_vlan", "edit_vlan"}:
            raise ValueError(f"Unknown command: {command}")

        config = self._config(device, args)
        exists = self._profile_exists(parent, config["vlan_id"])
        if command == "add_vlan" and exists:
            raise ValueError(f"VLAN {parent}.{config['vlan_id']} already exists")
        if command == "add_vlan" and str(ipaddress.ip_interface(config["address"]).ip) in _interface_addresses(parent):
            raise ValueError(
                f"{config['address']} is already assigned to parent {parent}; move it off the parent before adding the VLAN"
            )
        if command == "edit_vlan" and self._owned_profile(parent, config["vlan_id"]) is None:
            raise ValueError(f"VLAN {parent}.{config['vlan_id']} is not managed by IoTSploit")
        self._run_privileged("vlan-add" if command == "add_vlan" else "vlan-edit", config)
        return f"{'Added' if command == 'add_vlan' else 'Updated'} VLAN {parent}.{config['vlan_id']}"

    def _reset_impl(self, device: Device) -> bool:
        self._parent(device)
        return True

    def _close_impl(self, device: Device) -> bool:
        self._parent(device)
        return True
