#!/usr/bin/env python
"""Device and driver commands, answered by the running backend.

The backend owns the drivers and the hardware, and the UI talks to it over the
same routes. Asking it here, rather than loading a second copy of the drivers
in the shell, is what keeps the shell and the UI showing the same devices and
the same driver on/off state.
"""

import json
import os
import shlex
from urllib.parse import quote

import cmd2
import requests
from cmd2 import ansi
from .base_commands import BaseCommands
from iotsploit_cli import output
from iotsploit_django.tools.monitor_mgr import SystemMonitor
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger
from iotsploit_mcp.adapters.django_http_client import DjangoHttpClient, DjangoHttpError

logger = iots_logger.get_logger(__name__)

# Flashing a board or bringing up a VLAN takes longer than the client's usual
# few seconds. Ctrl+C stops waiting sooner.
_DEVICE_TIMEOUT_S = 600


def _argument_value(text):
    """`vlan_id=67` sends 67, `enabled=true` sends True, anything else a string."""
    try:
        return json.loads(text)
    except ValueError:
        return text


class DeviceCommands(BaseCommands):
    """Device-related commands for the SAT Shell"""

    def _backend(self, method, path, payload=None):
        """One backend call, or None after telling the operator why it failed."""
        client = DjangoHttpClient(
            base_url=os.getenv("IOTSPLOIT_DJANGO_API_BASE_URL", "http://127.0.0.1:8888"),
            timeout_s=_DEVICE_TIMEOUT_S,
        )
        try:
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path, json=payload)
        except DjangoHttpError as error:
            if isinstance(error.__cause__, requests.ConnectionError):
                self.perror("The backend isn't running. Run runserver first.")
                return None
            try:
                message = json.loads(error.response_text or "").get("message") or str(error)
            except (ValueError, AttributeError):
                message = str(error)
            self.perror(message)
            return None
        if response.get("status") == "error":
            self.perror(response.get("message", "The backend reported an error."))
            return None
        return response

    @cmd2.with_category('Device Commands')
    def do_device_info(self, arg):
        'Show IoTSploit Host Info'
        pi_monitor = SystemMonitor.create_monitor("raspberry_pi")
        device_info = SystemMonitor.monitor_device(pi_monitor)

        rows = []
        for key, value in device_info.items():
            if isinstance(value, dict):
                rows.append([key, ""])
                for sub_key, sub_value in value.items():
                    rows.append([f"  {sub_key}", str(sub_value)])
            else:
                rows.append([key, str(value)])
        self.poutput(output.table(["FIELD", "VALUE"], rows))

    @cmd2.with_category('Device Commands')
    def do_list_device_drivers(self, arg):
        'List the device drivers, whether each is enabled, and whether it can run here'
        response = self._backend("GET", "/api/list_device_drivers/")
        if response is None:
            return
        drivers = response.get("driver_info") or []
        if not drivers:
            self.poutput("No device drivers available.")
            return

        states = self._backend("GET", "/api/get_driver_states/")
        enabled_of = {}
        if states is not None:
            enabled_of = {name: state.get("enabled", True) for name, state in (states.get("drivers") or {}).items()}

        rows = []
        for driver in sorted(drivers, key=lambda d: d["name"]):
            name = driver["name"]
            enabled = enabled_of.get(name, True)
            availability = driver.get("availability") or {}
            rows.append([
                name,
                ansi.style("enabled", fg=ansi.Fg.GREEN) if enabled else ansi.style("disabled", fg=ansi.Fg.RED),
                output.available_mark(availability.get("available", True), availability.get("reason")),
            ])
        self.poutput(output.table(["DRIVER", "STATE", "AVAILABLE"], rows))
        enabled_count = sum(1 for driver in drivers if enabled_of.get(driver["name"], True))
        self.poutput(f"{len(drivers)} drivers · {enabled_count} enabled")

    do_lsdrv = do_list_device_drivers
    # driver status now shows the same table as driver list.
    do_get_driver_states = do_gds = do_list_device_drivers

    @cmd2.with_category('Device Commands')
    def do_list_devices(self, arg):
        'Scan with every driver and list the devices found'
        response = self._backend("POST", "/api/list_devices/")
        if response is None:
            return
        devices = response.get("devices") or []
        if not devices:
            self.poutput("No devices found.")
            return
        rows = [
            [
                ansi.style(device["device_id"], fg=ansi.Fg.GREEN),
                device.get("name", ""),
                device.get("driver", ""),
            ]
            for device in devices
        ]
        self.poutput(output.table(["DEVICE ID", "NAME", "DRIVER"], rows))
        self.poutput(f"{len(devices)} device{'' if len(devices) == 1 else 's'}")

    do_lsdev = do_scan_devices = do_scan = do_list_devices

    @cmd2.with_category('Device Commands')
    def do_execute_device_command(self, arg):
        'Run a command on a device. Usage: device run <device_id> <command> [key=value ...]'
        try:
            words = shlex.split(arg or "")
        except ValueError as error:
            self.perror(f"Cannot read the arguments: {error}")
            return
        if len(words) < 2:
            self.perror("Usage: device run <device_id> <command> [key=value ...]")
            self.poutput("See 'device list' for device ids and 'driver commands <driver>' for commands.")
            return
        device_id, command, pairs = words[0], words[1], words[2:]

        args = {}
        for pair in pairs:
            key, separator, value = pair.partition("=")
            if not separator or not key:
                self.perror(f"Arguments are key=value; got '{pair}'.")
                return
            args[key] = _argument_value(value)

        # Commands are routed by driver, and a scan is what knows which driver
        # owns a device id.
        listing = self._backend("POST", "/api/list_devices/")
        if listing is None:
            return
        driver = next(
            (device.get("driver") for device in listing.get("devices") or [] if device["device_id"] == device_id),
            None,
        )
        if driver is None:
            self.perror(f"No device '{device_id}'. See 'device list'.")
            return

        response = self._backend(
            "POST",
            f"/api/execute_device_command/{quote(driver, safe='')}/",
            {"command": command, "device_id": device_id, "args": args},
        )
        if response is None:
            return
        result = response.get("result")
        if result is None or isinstance(result, str):
            self.poutput(ansi.style(result or "Done.", fg=ansi.Fg.GREEN))
        else:
            self.poutput(json.dumps(result, indent=2, default=str))

    do_dc = do_execute_device_command

    @cmd2.with_category('Device Commands')
    def do_initialize_devices(self, arg):
        'Close and reopen every device in the backend, including ones plugged in since it started'
        # Some drivers (ESP32, the FPGA) refuse commands until their device is
        # initialized and connected. runserver does that for what is plugged in
        # at start; this is the same request, for anything plugged in since.
        if not Input_Mgr.Instance().yes_no_input(
            "This closes and reopens every device, in the UI too. Continue?", default=False
        ):
            self.poutput("Cancelled.")
            return
        response = self._backend("POST", "/api/initialize_devices/")
        if response is None:
            return
        rows = []
        for driver, result in (response.get("results") or {}).items():
            if not isinstance(result, dict):
                continue
            if result.get("status") == "error":
                rows.append([driver, "", ansi.style(result.get("message", ""), fg=ansi.Fg.RED)])
                continue
            for device in result.get("devices") or []:
                ok = device.get("status") == "success"
                rows.append([
                    driver,
                    str(device.get("device", "")),
                    ansi.style(str(device.get("message", "")), fg=ansi.Fg.GREEN if ok else ansi.Fg.RED),
                ])
        if rows:
            self.poutput(output.table(["DRIVER", "DEVICE", "RESULT"], rows))
        else:
            self.poutput("No devices to initialize.")

    do_initdev = do_initialize_devices

    @cmd2.with_category('Device Commands')
    def do_list_device_commands(self, arg):
        'List the commands a driver supports. Usage: driver commands <driver>'
        driver = (arg or "").strip()
        if not driver:
            self.perror("Usage: driver commands <driver>. See 'driver list'.")
            return
        response = self._backend("GET", f"/api/list_device_commands/{quote(driver, safe='')}/")
        if response is None:
            return
        commands = response.get("commands") or {}
        if not commands:
            self.poutput(f"{driver} has no commands.")
            return
        parameters = response.get("command_parameters") or {}
        rows = []
        has_required = False
        for name, description in commands.items():
            params = []
            for key, spec in (parameters.get(name) or {}).items():
                required = spec.get("required")
                has_required = has_required or required
                params.append(f"{key}*" if required else key)
            rows.append([name, ", ".join(params), description])
        self.poutput(output.table(["COMMAND", "PARAMETERS", "DESCRIPTION"], rows))
        if has_required:
            self.poutput("* required")

    do_lscmd = do_list_device_commands

    @cmd2.with_category('Device Commands')
    def do_enable_driver(self, arg):
        'Enable a device driver. Usage: driver enable <driver>'
        driver = (arg or "").strip()
        if not driver:
            self.perror("Usage: driver enable <driver>. See 'driver list'.")
            return
        if self._backend("POST", "/api/enable_driver/", {"driver_name": driver}) is not None:
            self.poutput(ansi.style(f"Enabled {driver}.", fg=ansi.Fg.GREEN))

    do_ed = do_enable_driver

    @cmd2.with_category('Device Commands')
    def do_disable_driver(self, arg):
        'Disable a device driver and close its devices. Usage: driver disable <driver>'
        driver = (arg or "").strip()
        if not driver:
            self.perror("Usage: driver disable <driver>. See 'driver list'.")
            return
        if not Input_Mgr.Instance().yes_no_input(
            f"Disabling {driver} closes its devices, in the UI too. Continue?", default=False
        ):
            self.poutput("Cancelled.")
            return
        response = self._backend("POST", "/api/disable_driver/", {"driver_name": driver})
        if response is None:
            return
        self.poutput(ansi.style(f"Disabled {driver}.", fg=ansi.Fg.GREEN))
        closed = response.get("closed_devices") or []
        if closed:
            self.poutput(f"Closed {len(closed)} device(s): {', '.join(closed)}")

    do_dd = do_disable_driver
