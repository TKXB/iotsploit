"""List the host's USB devices and describe the one the operator picks.

Doubles as the worked example for a command whose parameter offers a list:
`describe` cannot know what is plugged in when the driver is imported, so it
declares the parameter statically and fills the options in
``get_command_parameters``, which every caller -- the Drivers page form, the
CLI and MCP -- already asks for the moment it needs to collect input.
"""

from __future__ import annotations

from typing import Any, Optional

import usb.core
import usb.util

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import Device, DeviceType


USB_PARAMETER = "usb_device"

# What a hub reports as its class, so a list of 23 devices reads as devices.
_CLASSES = {
    0x00: "per-interface",
    0x02: "communications",
    0x03: "HID",
    0x07: "printer",
    0x08: "mass storage",
    0x09: "hub",
    0x0E: "video",
    0xE0: "wireless",
    0xEF: "miscellaneous",
    0xFF: "vendor-specific",
}


def _string(device: usb.core.Device, index: int) -> str:
    """A descriptor string, or nothing.

    Reading one talks to the device, which an unprivileged process is often
    not allowed to do. That is the normal case on a developer box, not an
    error worth failing an enumeration over.
    """
    if not index:
        return ""
    try:
        return (usb.util.get_string(device, index) or "").strip()
    except (usb.core.USBError, ValueError, NotImplementedError):
        return ""


def _address(device: usb.core.Device) -> str:
    """Where the device is, which is the only thing that stays unique.

    Two identical adapters share a vendor and product id and often report no
    serial number at all, so the bus position is what a command can act on.
    """
    return f"{device.bus:03d}:{device.address:03d}"


def _label(device: usb.core.Device) -> str:
    ids = f"{device.idVendor:04x}:{device.idProduct:04x}"
    name = " ".join(
        part
        for part in (_string(device, device.iManufacturer), _string(device, device.iProduct))
        if part
    )
    kind = _CLASSES.get(device.bDeviceClass, f"class 0x{device.bDeviceClass:02x}")
    return f"{name or kind} [{ids}] at {_address(device)}"


def _devices() -> list[usb.core.Device]:
    found = usb.core.find(find_all=True)
    return sorted(found or (), key=lambda device: (device.bus, device.address))


class UsbExplorerDriver(BaseDeviceDriver):
    REQUIRES = ("module:usb",)

    def __init__(self):
        super().__init__({
            "Name": "USB Explorer",
            "Description": "List the USB devices on this host and describe one",
        })
        self.supported_commands = {
            "list_usb": "List every USB device this host can see",
            "describe": {
                "description": "Describe one USB device",
                "parameters": {
                    USB_PARAMETER: {
                        "type": "str",
                        "required": True,
                        "description": "Which device to describe",
                        # Filled in live below; declared here so a caller that
                        # reads the static declaration still knows the shape.
                        "options": [],
                    },
                },
            },
        }

    def get_command_parameters(self) -> dict[str, dict[str, Any]]:
        """The declaration with what is plugged in right now filled in.

        Copied rather than mutated: the base hands back the live
        `supported_commands` entries, and writing this scan into them would
        leave one host's devices in the declaration for good.
        """
        options = [{"value": _address(device), "label": _label(device)} for device in _devices()]
        return {
            command: {
                name: {**spec, "options": options} if name == USB_PARAMETER else spec
                for name, spec in parameters.items()
            }
            for command, parameters in super().get_command_parameters().items()
        }

    def _scan_impl(self) -> list[Device]:
        return [
            Device(
                device_id="usb_explorer_host",
                name="USB Explorer (this host)",
                device_type=DeviceType.USB,
                attributes={"devices": len(_devices())},
            )
        ]

    def _initialize_impl(self, device: Device) -> bool:
        return True

    def _connect_impl(self, device: Device) -> bool:
        return True

    def _command_impl(self, device: Device, command: str, args: Optional[dict] = None) -> str:
        if command == "list_usb":
            found = _devices()
            if not found:
                return "No USB devices found."
            return "\n".join(_label(item) for item in found)

        if command != "describe":
            raise ValueError(f"Unknown command: {command}")

        address = str((args or {}).get(USB_PARAMETER, "")).strip()
        if not address:
            raise ValueError("Pick a USB device to describe")
        chosen = next((item for item in _devices() if _address(item) == address), None)
        if chosen is None:
            raise ValueError(f"No USB device at {address}; rescan and pick again")

        return "\n".join([
            f"Address:      {_address(chosen)}",
            f"Vendor:       0x{chosen.idVendor:04x} {_string(chosen, chosen.iManufacturer)}".rstrip(),
            f"Product:      0x{chosen.idProduct:04x} {_string(chosen, chosen.iProduct)}".rstrip(),
            f"Serial:       {_string(chosen, chosen.iSerialNumber) or 'not reported'}",
            f"Class:        {_CLASSES.get(chosen.bDeviceClass, f'0x{chosen.bDeviceClass:02x}')}",
            f"USB version:  {chosen.bcdUSB >> 8}.{(chosen.bcdUSB >> 4) & 0xF}",
            f"Configs:      {chosen.bNumConfigurations}",
        ])

    def _reset_impl(self, device: Device) -> bool:
        return True

    def _close_impl(self, device: Device) -> bool:
        return True
