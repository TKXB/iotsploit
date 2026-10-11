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
from iotsploit_django.tools.monitor_mgr import SystemMonitor
from iotsploit_django.tools.input_mgr import Input_Mgr
from iotsploit_core.utils import iots_logger
from iotsploit_mcp.adapters.django_http_client import DjangoHttpClient, DjangoHttpError

logger = iots_logger.get_logger(__name__)

# Flashing a board or bringing up a VLAN takes longer than the client's usual
# few seconds. Ctrl+C stops waiting sooner.
_DEVICE_TIMEOUT_S = 600


def _backend(method, path, payload=None):
    """One backend call, or None after saying why it failed."""
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
            logger.error(ansi.style("The backend isn't running. Run runserver first.", fg=ansi.Fg.RED))
            return None
        try:
            message = json.loads(error.response_text or "").get("message") or str(error)
        except (ValueError, AttributeError):
            message = str(error)
        logger.error(ansi.style(message, fg=ansi.Fg.RED))
        return None
    if response.get("status") == "error":
        logger.error(ansi.style(response.get("message", "The backend reported an error."), fg=ansi.Fg.RED))
        return None
    return response


def _argument_value(text):
    """`vlan_id=67` sends 67, `enabled=true` sends True, anything else a string."""
    try:
        return json.loads(text)
    except ValueError:
        return text


class DeviceCommands(BaseCommands):
    """Device-related commands for the SAT Shell"""

    @cmd2.with_category('Device Commands')
    def do_device_info(self, arg):
        'Show IoTSploit Host Info'
        logger.info(ansi.style("Host Device Info:", fg=ansi.Fg.CYAN))

        pi_monitor = SystemMonitor.create_monitor("raspberry_pi")
        device_info = SystemMonitor.monitor_device(pi_monitor)

        for key, value in device_info.items():
            if isinstance(value, dict):
                logger.info(ansi.style(f"  {key}:", fg=ansi.Fg.CYAN))
                for sub_key, sub_value in value.items():
                    logger.info(ansi.style(f"    {sub_key}: {sub_value}", fg=ansi.Fg.CYAN))
            else:
                logger.info(ansi.style(f"  {key}: {value}", fg=ansi.Fg.CYAN))

    @cmd2.with_category('Device Commands')
    def do_list_device_drivers(self, arg):
        'List the device drivers and whether each can run on this host'
        response = _backend("GET", "/api/list_device_drivers/")
        if response is None:
            return
        drivers = response.get("driver_info") or []
        if not drivers:
            logger.info(ansi.style("No device drivers available.", fg=ansi.Fg.YELLOW))
            return
        for driver in drivers:
            availability = driver.get("availability") or {}
            if availability.get("available", True):
                logger.info(ansi.style(f"  {driver['name']}", fg=ansi.Fg.GREEN))
                continue
            logger.info(
                ansi.style(f"  {driver['name']}", fg=ansi.Fg.YELLOW)
                + f"  unavailable: {availability.get('reason') or 'unknown reason'}"
            )
            if availability.get("hint"):
                logger.info(f"      {availability['hint']}")

    do_lsdrv = do_list_device_drivers

    @cmd2.with_category('Device Commands')
    def do_list_devices(self, arg):
        'Scan with every driver and list the devices found'
        response = _backend("POST", "/api/list_devices/")
        if response is None:
            return
        devices = response.get("devices") or []
        if not devices:
            logger.info(ansi.style("No devices found.", fg=ansi.Fg.YELLOW))
            return
        driver_width = max(len(device.get("driver", "")) for device in devices)
        id_width = max(len(device["device_id"]) for device in devices)
        for device in devices:
            logger.info(
                ansi.style(f"{device.get('driver', ''):<{driver_width}}  ", fg=ansi.Fg.CYAN)
                + ansi.style(f"{device['device_id']:<{id_width}}  ", fg=ansi.Fg.GREEN)
                + device.get("name", "")
            )

    do_lsdev = do_scan_devices = do_scan = do_list_devices

    @cmd2.with_category('Device Commands')
    def do_execute_device_command(self, arg):
        'Run a command on a device. Usage: device run <device_id> <command> [key=value ...]'
        try:
            words = shlex.split(arg or "")
        except ValueError as error:
            logger.error(ansi.style(f"Cannot read the arguments: {error}", fg=ansi.Fg.RED))
            return
        if len(words) < 2:
            logger.error(ansi.style("Usage: device run <device_id> <command> [key=value ...]", fg=ansi.Fg.RED))
            logger.info("See 'device list' for device ids and 'driver commands <driver>' for commands.")
            return
        device_id, command, pairs = words[0], words[1], words[2:]

        args = {}
        for pair in pairs:
            key, separator, value = pair.partition("=")
            if not separator or not key:
                logger.error(ansi.style(f"Arguments are key=value; got '{pair}'.", fg=ansi.Fg.RED))
                return
            args[key] = _argument_value(value)

        # Commands are routed by driver, and a scan is what knows which driver
        # owns a device id.
        listing = _backend("POST", "/api/list_devices/")
        if listing is None:
            return
        driver = next(
            (device.get("driver") for device in listing.get("devices") or [] if device["device_id"] == device_id),
            None,
        )
        if driver is None:
            logger.error(ansi.style(f"No device '{device_id}'. See 'device list'.", fg=ansi.Fg.RED))
            return

        response = _backend(
            "POST",
            f"/api/execute_device_command/{quote(driver, safe='')}/",
            {"command": command, "device_id": device_id, "args": args},
        )
        if response is None:
            return
        result = response.get("result")
        if result is None or isinstance(result, str):
            logger.info(ansi.style(result or "Done.", fg=ansi.Fg.GREEN))
        else:
            logger.info(json.dumps(result, indent=2, default=str))

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
            logger.info("Cancelled.")
            return
        response = _backend("POST", "/api/initialize_devices/")
        if response is None:
            return
        for driver, result in (response.get("results") or {}).items():
            if not isinstance(result, dict):
                continue
            for device in result.get("devices") or []:
                ok = device.get("status") == "success"
                logger.info(
                    ansi.style(f"  {driver}  {device.get('device')}: ", fg=ansi.Fg.GREEN if ok else ansi.Fg.RED)
                    + str(device.get("message", ""))
                )
            if result.get("status") == "error":
                logger.error(ansi.style(f"  {driver}: {result.get('message', '')}", fg=ansi.Fg.RED))

    do_initdev = do_initialize_devices

    @cmd2.with_category('Device Commands')
    def do_list_device_commands(self, arg):
        'List the commands a driver supports. Usage: driver commands <driver>'
        driver = (arg or "").strip()
        if not driver:
            logger.error(ansi.style("Usage: driver commands <driver>. See 'driver list'.", fg=ansi.Fg.RED))
            return
        response = _backend("GET", f"/api/list_device_commands/{quote(driver, safe='')}/")
        if response is None:
            return
        commands = response.get("commands") or {}
        if not commands:
            logger.info(ansi.style(f"{driver} has no commands.", fg=ansi.Fg.YELLOW))
            return
        parameters = response.get("command_parameters") or {}
        width = max(len(name) for name in commands)
        for name, description in commands.items():
            logger.info(ansi.style(f"  {name:<{width}}", fg=ansi.Fg.GREEN) + f"  {description}")
            for key, spec in (parameters.get(name) or {}).items():
                required = " (required)" if spec.get("required") else ""
                logger.info(f"  {'':<{width}}    {key}={spec.get('type', 'str')}{required}  {spec.get('description', '')}")

    do_lscmd = do_list_device_commands

    @cmd2.with_category('Device Commands')
    def do_get_driver_states(self, arg):
        'Show which device drivers are enabled'
        response = _backend("GET", "/api/get_driver_states/")
        if response is None:
            return
        states = response.get("drivers") or {}
        if not states:
            logger.info(ansi.style("No device drivers found.", fg=ansi.Fg.YELLOW))
            return
        logger.info(ansi.style(
            f"Total: {response.get('driver_count', len(states))} | "
            f"Enabled: {response.get('enabled_count', 0)} | Disabled: {response.get('disabled_count', 0)}",
            fg=ansi.Fg.BLUE,
        ))
        width = max(len(name) for name in states)
        for name, state in states.items():
            enabled = state.get("enabled", True)
            logger.info(
                ansi.style(f"  {name:<{width}}  ", fg=ansi.Fg.CYAN)
                + ansi.style("Enabled" if enabled else "Disabled", fg=ansi.Fg.GREEN if enabled else ansi.Fg.RED)
            )

    do_gds = do_get_driver_states

    @cmd2.with_category('Device Commands')
    def do_enable_driver(self, arg):
        'Enable a device driver. Usage: driver enable <driver>'
        driver = (arg or "").strip()
        if not driver:
            logger.error(ansi.style("Usage: driver enable <driver>. See 'driver status'.", fg=ansi.Fg.RED))
            return
        if _backend("POST", "/api/enable_driver/", {"driver_name": driver}) is not None:
            logger.info(ansi.style(f"Enabled {driver}.", fg=ansi.Fg.GREEN))

    do_ed = do_enable_driver

    @cmd2.with_category('Device Commands')
    def do_disable_driver(self, arg):
        'Disable a device driver and close its devices. Usage: driver disable <driver>'
        driver = (arg or "").strip()
        if not driver:
            logger.error(ansi.style("Usage: driver disable <driver>. See 'driver status'.", fg=ansi.Fg.RED))
            return
        if not Input_Mgr.Instance().yes_no_input(
            f"Disabling {driver} closes its devices, in the UI too. Continue?", default=False
        ):
            logger.info("Cancelled.")
            return
        response = _backend("POST", "/api/disable_driver/", {"driver_name": driver})
        if response is None:
            return
        logger.info(ansi.style(f"Disabled {driver}.", fg=ansi.Fg.GREEN))
        closed = response.get("closed_devices") or []
        if closed:
            logger.info(f"Closed {len(closed)} device(s): {', '.join(closed)}")

    do_dd = do_disable_driver
