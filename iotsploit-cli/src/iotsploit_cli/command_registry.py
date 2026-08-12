"""Canonical IoTSploit CLI command metadata.

This module is intentionally free of Django and cmd2 imports.  It is the
shared contract used by command parsers, help output, and the live palette.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class ActionSpec:
    """Describe one canonical ``resource action`` command."""

    name: str
    summary: str
    legacy_commands: Tuple[str, ...]


@dataclass(frozen=True)
class ResourceSpec:
    """Describe a top-level command resource and its actions."""

    name: str
    summary: str
    actions: Tuple[ActionSpec, ...]


def _action(name: str, summary: str, *legacy: str) -> ActionSpec:
    return ActionSpec(name, summary, legacy)


RESOURCE_SPECS: Tuple[ResourceSpec, ...] = (
    ResourceSpec("host", "Show information about the IoTSploit host", (
        _action("show", "Show host system information", "device_info"),
    )),
    ResourceSpec("device", "Discover, select, import, and use devices", (
        _action("list", "List configured devices", "list_devices", "lsdev"),
        _action("scan", "Scan for available devices", "scan_devices", "scan"),
        _action("initialize", "Initialize available devices", "initialize_devices", "initdev"),
        _action("select", "Select the active device", "select_device", "sd", "switch_device"),
        _action("run", "Run a command on the active device", "execute_device_command", "dc"),
        _action("import", "Import devices from JSON", "device_import", "dimport"),
    )),
    ResourceSpec("driver", "Inspect and manage device drivers", (
        _action("list", "List available device drivers", "list_device_drivers", "lsdrv"),
        _action("commands", "List commands supported by a driver", "list_device_commands", "lscmd"),
        _action("status", "Show driver enablement state", "get_driver_states", "gds"),
        _action("enable", "Enable a device driver", "enable_driver", "ed"),
        _action("disable", "Disable a device driver", "disable_driver", "dd"),
    )),
    ResourceSpec("firmware", "Manage and flash registered firmware", (
        _action("list", "List registered firmware", "list_firmware", "lsfw"),
        _action("add", "Register a firmware image", "add_firmware", "addfw"),
        _action("download", "Download a firmware image", "download_firmware", "dlfw"),
        _action("flash", "Flash registered firmware", "flash_firmware", "flashfw"),
        _action("remove", "Remove registered firmware", "remove_firmware", "rmfw"),
    )),
    ResourceSpec("plugin", "Discover and execute exploit plugins", (
        _action("list", "List available plugins", "list_plugins", "lsp"),
        _action("run", "Execute one plugin", "execute_plugin", "exec"),
        _action("run-all", "Execute all plugins", "exploit"),
        _action("refresh", "Refresh installed plugins", "flash_plugins", "fp"),
    )),
    ResourceSpec("target", "Select, edit, import, and export targets", (
        _action("list", "List available targets", "list_targets", "lst"),
        _action("select", "Select the active target", "target_select"),
        _action("edit", "Edit a target", "edit_target", "et"),
        _action("observations", "Show what scans discovered about a target", "target_observations", "obs"),
        _action("import", "Import targets from JSON", "target_import"),
        _action("export", "Export targets to JSON", "target_export"),
    )),
    ResourceSpec("service", "Control IoTSploit background services", (
        _action("start", "Start backend services", "runserver"),
        _action("stop", "Stop backend services", "stop_server"),
        _action("status", "Show backend service status"),
    )),
    ResourceSpec("wifi", "Manage Wi-Fi connectivity", (
        _action("connect", "Connect to a Wi-Fi network", "connect_wifi"),
    )),
    ResourceSpec("config", "Change interactive shell configuration", (
        _action("set", "Set logging level or output format", "set_log_level", "sll", "set_log_format", "slf"),
    )),
)

RESOURCE_BY_NAME: Dict[str, ResourceSpec] = {
    resource.name: resource for resource in RESOURCE_SPECS
}

LEGACY_REPLACEMENTS: Dict[str, str] = {
    legacy: f"{resource.name} {action.name}"
    for resource in RESOURCE_SPECS
    for action in resource.actions
    for legacy in action.legacy_commands
}
LEGACY_REPLACEMENTS.update({
    "ls": "shell ls (or !ls)",
    "lsusb": "device scan",
    "quit": "exit",
})

ESSENTIAL_COMMANDS: Tuple[Tuple[str, str], ...] = (
    ("help", "Show the command overview or detailed command help"),
    ("history", "Show command history"),
    ("exit", "Exit IoTSploit"),
)

ADVANCED_COMMANDS: Tuple[str, ...] = (
    "alias", "edit", "macro", "run_pyscript", "run_script", "set", "shell", "shortcuts"
)


def resource_entries(prefix: str = "") -> Iterable[Tuple[str, str]]:
    """Yield canonical top-level resources matching *prefix*."""
    normalized = prefix.lower()
    for resource in RESOURCE_SPECS:
        if resource.name.startswith(normalized):
            yield resource.name, resource.summary


def action_entries(resource_name: str, prefix: str = "") -> Iterable[Tuple[str, str]]:
    """Yield actions for a canonical resource matching *prefix*."""
    resource = RESOURCE_BY_NAME.get(resource_name.lower())
    if resource is None:
        return
    normalized = prefix.lower()
    for action in resource.actions:
        if action.name.startswith(normalized):
            yield action.name, action.summary
