from __future__ import annotations

import logging
import re
import select
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import usb.core
import usb.util

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import DeviceType, USBDevice

logger = logging.getLogger(__name__)


class UbertoothDriver(BaseDeviceDriver):
    VENDOR_ID = 0x1D50
    PRODUCT_ID = 0x6002

    def __init__(self):
        super().__init__()
        self._active_process: Optional[subprocess.Popen] = None
        self._process_lock = threading.Lock()
        self._ubertooth_device = 0
        self.supported_commands = {
            "get_info": "Get device info (firmware, board ID, serial)",
            "identify": "Flash LEDs to identify device",
            "stop_op": "Stop current Ubertooth operation",
            "ble_scan": "Scan BLE advertisements",
        }

    def _device_flag(self) -> str:
        return f"-U{self._ubertooth_device}"

    def _run_cmd(self, cmd: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
        full_cmd = cmd + [self._device_flag()]
        logger.debug("Running command: %s", " ".join(full_cmd))
        return subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)

    def _run_streaming(
        self,
        cmd: List[str],
        line_parser,
        timeout: int = 30,
    ) -> List[Dict[str, Any]]:
        full_cmd = cmd + [self._device_flag()]
        logger.debug("Running streaming command: %s", " ".join(full_cmd))
        results: List[Dict[str, Any]] = []

        with self._process_lock:
            self._active_process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            proc = self._active_process

        assert proc.stdout is not None
        start = time.time()
        try:
            while True:
                if time.time() - start > timeout:
                    break
                if proc.poll() is not None:
                    break
                readable, _, _ = select.select([proc.stdout], [], [], 0.2)
                if not readable:
                    continue
                line = proc.stdout.readline()
                if not line:
                    continue
                parsed = line_parser(line.strip())
                if parsed:
                    results.append(parsed)
        finally:
            self._stop_active()
        return results

    def _stop_active(self):
        with self._process_lock:
            if self._active_process:
                try:
                    self._active_process.terminate()
                    self._active_process.wait(timeout=3)
                except Exception:
                    try:
                        self._active_process.kill()
                    except Exception:
                        pass
                finally:
                    self._active_process = None
        try:
            self._run_cmd(["ubertooth-util", "-S"], timeout=5)
        except Exception as e:
            logger.debug("Failed to send stop to ubertooth-util: %s", e)

    def _scan_impl(self) -> list:
        usb_devices = usb.core.find(
            find_all=True,
            idVendor=self.VENDOR_ID,
            idProduct=self.PRODUCT_ID,
        )
        if usb_devices is None:
            return []

        found_devices = []
        for usb_dev in usb_devices:
            try:
                serial_number = usb.util.get_string(usb_dev, usb_dev.iSerialNumber) or "unknown"
                device = USBDevice(
                    device_id=f"ubertooth_{serial_number}",
                    name="Ubertooth One",
                    device_type=DeviceType.USB,
                    vendor_id=hex(self.VENDOR_ID),
                    product_id=hex(self.PRODUCT_ID),
                    attributes={"serial_number": serial_number},
                )
                found_devices.append(device)
            except usb.core.USBError as e:
                logger.error("Could not access Ubertooth device: %s", e)
        return found_devices

    def _initialize_impl(self, device: USBDevice) -> bool:
        if device.device_type != DeviceType.USB:
            raise ValueError("Ubertooth driver only supports USB devices")
        result = self._run_cmd(["ubertooth-util", "-v"], timeout=8)
        return result.returncode == 0

    def _connect_impl(self, device: USBDevice) -> bool:
        dev = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)
        return dev is not None

    def _command_impl(self, device: USBDevice, command: str, args: Optional[Dict] = None):
        if not isinstance(args, dict):
            args = {}

        if command == "get_info":
            return self._handle_get_info()
        if command == "identify":
            result = self._run_cmd(["ubertooth-util", "-I"], timeout=8)
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        if command == "stop_op":
            self._stop_active()
            return {"status": "success"}
        if command == "ble_scan":
            return self._handle_ble_scan(args)
        raise ValueError(f"Unsupported command: {command}")

    def _handle_get_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {}

        ver = self._run_cmd(["ubertooth-util", "-v"], timeout=8)
        info["firmware"] = (ver.stdout or ver.stderr).strip()

        compile_info = self._run_cmd(["ubertooth-util", "-V"], timeout=8)
        info["compile_info"] = (compile_info.stdout or compile_info.stderr).strip()

        board = self._run_cmd(["ubertooth-util", "-b"], timeout=8)
        info["board_id"] = (board.stdout or board.stderr).strip()

        serial = self._run_cmd(["ubertooth-util", "-s"], timeout=8)
        info["serial"] = (serial.stdout or serial.stderr).strip()

        part = self._run_cmd(["ubertooth-util", "-p"], timeout=8)
        info["part_id"] = (part.stdout or part.stderr).strip()

        return info

    def _handle_ble_scan(self, args: Dict[str, Any]) -> Dict[str, Any]:
        timeout = int(args.get("timeout", 10))
        channel = int(args.get("channel", 37))
        if channel not in (37, 38, 39):
            channel = 37

        state: Dict[str, Any] = {"current_mac": None}
        devices: Dict[str, Dict[str, Any]] = {}

        def parse_line(line: str) -> Optional[Dict[str, Any]]:
            if not line:
                return None

            if line.startswith("AdvA:"):
                match = re.search(r"AdvA:\s+([0-9a-f:]+)\s+\((\w+)\)", line, re.IGNORECASE)
                if not match:
                    return None
                mac = match.group(1).lower()
                addr_type = match.group(2).lower()
                state["current_mac"] = mac
                devices.setdefault(
                    mac,
                    {
                        "mac": mac,
                        "name": "",
                        "rssi": None,
                        "company": "",
                        "adv_type": "",
                        "address_type": addr_type,
                        "channel": channel,
                    },
                )
                devices[mac]["address_type"] = addr_type
                return {"type": "adva", "mac": mac}

            if line.startswith("Type:"):
                if state["current_mac"] and state["current_mac"] in devices:
                    devices[state["current_mac"]]["adv_type"] = line.split(":", 1)[1].strip()
                return {"type": "adv_type"}

            if line.startswith("Channel Index:"):
                if state["current_mac"] and state["current_mac"] in devices:
                    try:
                        devices[state["current_mac"]]["channel"] = int(line.split(":", 1)[1].strip())
                    except Exception:
                        pass
                return {"type": "channel"}

            if line.startswith("Company:"):
                if state["current_mac"] and state["current_mac"] in devices:
                    devices[state["current_mac"]]["company"] = line.split(":", 1)[1].strip()
                return {"type": "company"}

            if "rssi=" in line:
                match = re.search(r"rssi=(-?\d+)", line, re.IGNORECASE)
                if match and state["current_mac"] and state["current_mac"] in devices:
                    rssi = int(match.group(1))
                    prev = devices[state["current_mac"]]["rssi"]
                    if prev is None or rssi > prev:
                        devices[state["current_mac"]]["rssi"] = rssi
                return {"type": "rssi"}

            return None

        self._run_streaming(
            ["ubertooth-btle", "-n", f"-A{channel}"],
            parse_line,
            timeout=timeout,
        )

        result_devices = list(devices.values())
        result_devices.sort(key=lambda d: (d["rssi"] is None, -(d["rssi"] or -999)))
        return {"devices": result_devices, "count": len(result_devices)}

    def _reset_impl(self, device: USBDevice) -> bool:
        self._stop_active()
        result = self._run_cmd(["ubertooth-util", "-r"], timeout=10)
        return result.returncode == 0

    def _close_impl(self, device: USBDevice) -> bool:
        self._stop_active()
        return True

    def _recovery_impl(self, device: USBDevice, recovery_type: str, **kwargs) -> dict:
        raise NotImplementedError("Recovery operations are not implemented yet")

    def _get_supported_recovery_operations_impl(self) -> list:
        return []

