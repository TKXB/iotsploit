"""Canonical resource/action commands for the interactive CLI."""

import argparse
import shlex

import cmd2

from .base_commands import BaseCommands


def _parser(description):
    return cmd2.Cmd2ArgumentParser(description=description)


def _subcommands(parser):
    return parser.add_subparsers(dest="action", required=True)


host_parser = _parser("Show information about the IoTSploit host")
host_sub = _subcommands(host_parser)
host_sub.add_parser("show", help="show host system information").set_defaults(handler="do_device_info")

device_parser = _parser("Discover, select, import, and use devices")
device_sub = _subcommands(device_parser)
device_sub.add_parser("list", help="list configured devices").set_defaults(handler="do_list_devices")
device_sub.add_parser("scan", help="scan for available devices").set_defaults(handler="do_scan_devices")
device_sub.add_parser("initialize", help="initialize available devices").set_defaults(handler="do_initialize_devices")
device_select = device_sub.add_parser("select", help="select the active device")
device_select.add_argument("device", nargs="?")
device_select.set_defaults(handler="do_select_device", argument="device")
device_run = device_sub.add_parser("run", help="run a command on the active device")
device_run.add_argument("command", nargs=argparse.REMAINDER)
device_run.set_defaults(handler="do_execute_device_command", argument="command", join=True)
device_import = device_sub.add_parser("import", help="import devices from JSON")
device_import.add_argument("file")
device_import.set_defaults(handler="do_device_import", argument="file")

driver_parser = _parser("Inspect and manage device drivers")
driver_sub = _subcommands(driver_parser)
driver_sub.add_parser("list", help="list available drivers").set_defaults(handler="do_list_device_drivers")
driver_commands = driver_sub.add_parser("commands", help="list commands supported by a driver")
driver_commands.add_argument("driver", nargs="?")
driver_commands.set_defaults(handler="do_list_device_commands", argument="driver")
driver_sub.add_parser("status", help="show driver enablement state").set_defaults(handler="do_get_driver_states")
driver_enable = driver_sub.add_parser("enable", help="enable a driver")
driver_enable.add_argument("driver", nargs="?")
driver_enable.set_defaults(handler="do_enable_driver", argument="driver")
driver_disable = driver_sub.add_parser("disable", help="disable a driver")
driver_disable.add_argument("driver", nargs="?")
driver_disable.set_defaults(handler="do_disable_driver", argument="driver")

firmware_parser = _parser("Manage and flash registered firmware")
firmware_sub = _subcommands(firmware_parser)
firmware_sub.add_parser("list", help="list registered firmware").set_defaults(handler="do_list_firmware")
firmware_add = firmware_sub.add_parser("add", help="register a firmware image")
firmware_add.add_argument("name")
firmware_add.add_argument("path")
firmware_add.add_argument("device_type")
firmware_add.add_argument("version")
firmware_add.add_argument("--options", default=None, help="flash options as JSON")
firmware_add.set_defaults(handler="do_add_firmware", builder="firmware_add")
firmware_download = firmware_sub.add_parser("download", help="download a firmware image")
firmware_download.add_argument("url")
firmware_download.add_argument("output", nargs="?")
firmware_download.set_defaults(handler="do_download_firmware", builder="firmware_download")
firmware_flash = firmware_sub.add_parser("flash", help="flash registered firmware")
firmware_flash.add_argument("firmware")
firmware_flash.add_argument("device")
firmware_flash.add_argument("--options", default=None, help="flash options as JSON")
firmware_flash.set_defaults(handler="do_flash_firmware", builder="firmware_flash")
firmware_remove = firmware_sub.add_parser("remove", help="remove registered firmware")
firmware_remove.add_argument("firmware")
firmware_remove.set_defaults(handler="do_remove_firmware", argument="firmware")

plugin_parser = _parser("Discover and execute exploit plugins")
plugin_sub = _subcommands(plugin_parser)
plugin_sub.add_parser("list", help="list available plugins").set_defaults(handler="do_list_plugins")
plugin_run = plugin_sub.add_parser("run", help="execute one plugin")
plugin_run.add_argument("plugin", nargs="?")
plugin_run.set_defaults(handler="do_execute_plugin", argument="plugin")
plugin_sub.add_parser("run-all", help="execute all plugins").set_defaults(handler="do_exploit")
plugin_sub.add_parser("refresh", help="refresh installed plugins").set_defaults(handler="do_flash_plugins")

target_parser = _parser("Select, edit, import, and export targets")
target_sub = _subcommands(target_parser)
target_list = target_sub.add_parser("list", help="list available targets")
target_list.add_argument("target", nargs="?", help="show full detail for one target, or 'all'")
target_list.set_defaults(handler="do_list_targets", argument="target")
target_select = target_sub.add_parser("select", help="select the active target")
target_select.add_argument("target", nargs="?")
target_select.set_defaults(handler="do_target_select", argument="target")
target_edit = target_sub.add_parser("edit", help="edit a target")
target_edit.add_argument("target", nargs="?")
target_edit.set_defaults(handler="do_edit_target", argument="target")
target_import = target_sub.add_parser("import", help="import targets from JSON")
target_import.add_argument("file")
target_import.set_defaults(handler="do_target_import", argument="file")
target_obs = target_sub.add_parser("observations", help="show what scans discovered about a target")
target_obs.add_argument("target", nargs="?", help="defaults to the active target")
target_obs.set_defaults(handler="do_target_observations", argument="target")
target_export = target_sub.add_parser("export", help="export targets to JSON")
target_export.add_argument("file", nargs="?")
target_export.set_defaults(handler="do_target_export", argument="file")

service_parser = _parser("Control IoTSploit background services")
service_sub = _subcommands(service_parser)
service_sub.add_parser("start", help="start backend services").set_defaults(handler="do_runserver")
service_sub.add_parser("stop", help="stop backend services").set_defaults(handler="do_stop_server")
service_sub.add_parser("status", help="show backend service status").set_defaults(local_handler="service_status")

wifi_parser = _parser("Manage Wi-Fi connectivity")
wifi_sub = _subcommands(wifi_parser)
wifi_sub.add_parser("connect", help="connect to a Wi-Fi network").set_defaults(handler="do_connect_wifi")

config_parser = _parser("Change interactive shell configuration")
config_sub = _subcommands(config_parser)
config_set = config_sub.add_parser("set", help="set logging options")
config_set.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
config_set.add_argument("--log-format", choices=("standard", "compact", "plain"))
config_set.set_defaults(local_handler="config_set")


class ResourceCommands(BaseCommands):
    """Stable, discoverable resource/action command surface."""

    def _dispatch_resource_command(self, args):
        local_handler = getattr(args, "local_handler", None)
        if local_handler:
            return getattr(self, f"_{local_handler}")(args)

        argument = ""
        argument_name = getattr(args, "argument", None)
        if argument_name:
            value = getattr(args, argument_name, None)
            if isinstance(value, list):
                argument = " ".join(value)
            elif value is not None:
                argument = value
        builder = getattr(args, "builder", None)
        if builder:
            argument = getattr(self, f"_{builder}_argument")(args)
        return getattr(self, args.handler)(argument)

    @staticmethod
    def _firmware_add_argument(args):
        values = [args.name, args.path, args.device_type, args.version]
        if args.options:
            values.append(args.options)
        return shlex.join(values)

    @staticmethod
    def _firmware_download_argument(args):
        return shlex.join([value for value in (args.url, args.output) if value])

    @staticmethod
    def _firmware_flash_argument(args):
        values = [args.firmware, args.device]
        if args.options:
            values.append(args.options)
        return shlex.join(values)

    def _service_status(self, _args):
        services = (
            ("django", "django_server_process"),
            ("daphne", "daphne_server_process"),
            ("mcp", "mcp_bridge_process"),
            ("celery", "celery_worker_process"),
            ("celery-i", "interactive_worker_process"),
        )
        for name, attribute in services:
            process = getattr(self, attribute, None)
            running = process is not None and process.poll() is None
            self.poutput(f"{name:<8} {'running' if running else 'stopped'}")

    def _config_set(self, args):
        if not args.log_level and not args.log_format:
            self.perror("Specify --log-level and/or --log-format")
            return
        if args.log_level:
            self.do_set_log_level(args.log_level)
        if args.log_format:
            self.do_set_log_format(args.log_format)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(host_parser)
    def do_host(self, args):
        """Show information about the IoTSploit host."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(device_parser)
    def do_device(self, args):
        """Discover, select, import, and use devices."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(driver_parser)
    def do_driver(self, args):
        """Inspect and manage device drivers."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(firmware_parser)
    def do_firmware(self, args):
        """Manage and flash registered firmware."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(plugin_parser)
    def do_plugin(self, args):
        """Discover and execute exploit plugins."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(target_parser)
    def do_target(self, args):
        """Select, edit, import, and export targets."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(service_parser)
    def do_service(self, args):
        """Control IoTSploit background services."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(wifi_parser)
    def do_wifi(self, args):
        """Manage Wi-Fi connectivity."""
        return self._dispatch_resource_command(args)

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(config_parser)
    def do_config(self, args):
        """Change interactive shell configuration."""
        return self._dispatch_resource_command(args)
