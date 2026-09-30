"""Raw USB access to one selected USBTMC interface; no protocol judgement."""

from __future__ import annotations

import hashlib


def resource_key(device: dict) -> str:
    """Same identity as the desktop bridge; preserve arbitrary USB serials."""
    serial = device.get("serial") or ""
    identity = hashlib.sha256(serial.encode("utf-8")).hexdigest() if serial else (
        f"bus{device['bus']}-addr{device['address']}"
    )
    return f"usbtmc:{device['vid']:04x}-{device['pid']:04x}-{identity}/if{device['interface']}"


class USBTMCInterface:
    @staticmethod
    def discover() -> list[dict]:
        import usb.core
        import usb.util

        found = []
        for device in usb.core.find(find_all=True):
            try:
                for config in device:
                    for interface in config:
                        if (interface.bInterfaceClass, interface.bInterfaceSubClass) != (0xFE, 3):
                            continue
                        try:
                            serial = usb.util.get_string(device, device.iSerialNumber) if device.iSerialNumber else ""
                        except (usb.core.USBError, ValueError):
                            serial = ""
                        found.append({
                            "vid": device.idVendor, "pid": device.idProduct, "serial": serial or "",
                            "bus": device.bus, "address": device.address,
                            "configuration": config.bConfigurationValue,
                            "interface": interface.bInterfaceNumber,
                            "alternate_setting": interface.bAlternateSetting,
                            "label": f"{device.idVendor:04x}:{device.idProduct:04x} "
                                     f"{serial or 'no serial'} at {device.bus}:{device.address} "
                                     f"interface {interface.bInterfaceNumber}",
                        })
            finally:
                usb.util.dispose_resources(device)
        return found

    def __init__(self, selector: dict, *, lease=None, owner: str = "USBTMC"):
        import usb.core
        import usb.util

        if not isinstance(selector, dict) or not selector:
            raise ValueError("Select a USBTMC interface from rig discovery")
        for key, maximum in (("vid", 65535), ("pid", 65535), ("interface", 255),
                             ("configuration", 255), ("alternate_setting", 255),
                             ("bus", 255), ("address", 127)):
            if key in selector and (type(selector[key]) is not int or not 0 <= selector[key] <= maximum):
                raise ValueError(f"Invalid USB device {key}")
        if "serial" in selector and not isinstance(selector["serial"], str):
            raise ValueError("USB device serial must be a string")
        ignored = {"label", "bus", "address"} if selector.get("serial") else {"label"}
        matches = [item for item in self.discover() if all(
            item.get(key) == value for key, value in selector.items() if key not in ignored
        )]
        if len(matches) != 1:
            raise ValueError(f"USB selection matched {len(matches)} interfaces; rescan and select one")
        self.identity = matches[0]
        self.resource = resource_key(self.identity)
        self.lease, self.owner = lease, owner
        self.device = None
        self.detached = False
        self.claimed = False
        self._leased = False
        self.interface = self.identity["interface"]
        if lease is not None:
            lease.acquire(self.resource, owner)
            self._leased = True
        try:
            self.device = usb.core.find(bus=self.identity["bus"], address=self.identity["address"])
            if self.device is None:
                raise ValueError("Selected USB device disconnected")
            try:
                if self.device.is_kernel_driver_active(self.interface):
                    self.device.detach_kernel_driver(self.interface)
                    self.detached = True
            except NotImplementedError:
                pass
            active = self.device.get_active_configuration()
            if active.bConfigurationValue != self.identity["configuration"]:
                raise ValueError("Selected USB configuration is not active")
            usb.util.claim_interface(self.device, self.interface)
            self.claimed = True
            alt = self.identity["alternate_setting"]
            if alt:
                self.device.set_interface_altsetting(interface=self.interface, alternate_setting=alt)
            desc = active[(self.interface, alt)]
            endpoints = [ep.bEndpointAddress for ep in desc if (ep.bmAttributes & 3) == 2]
            self.ep_in = next(ep for ep in endpoints if ep & 0x80)
            self.ep_out = next(ep for ep in endpoints if not ep & 0x80)
            self.packet_size = next(ep.wMaxPacketSize for ep in desc if ep.bEndpointAddress == self.ep_in)
        except BaseException:
            self.close()
            raise

    def write(self, data: bytes, timeout: int) -> int:
        return self.device.write(self.ep_out, data, timeout=timeout)

    def read(self, size: int, timeout: int) -> bytes:
        return bytes(self.device.read(self.ep_in, size, timeout=timeout))

    def control(self, request_type: int, request: int, value: int, index: int, size: int, timeout: int) -> bytes:
        return bytes(self.device.ctrl_transfer(request_type, request, value, index, size, timeout=timeout))

    def clear_halt(self, endpoint: int) -> None:
        self.device.clear_halt(endpoint)

    def close(self) -> None:
        import usb.util

        device, self.device = self.device, None
        try:
            if device is not None:
                try:
                    if self.claimed:
                        usb.util.release_interface(device, self.interface)
                finally:
                    try:
                        if self.detached:
                            device.attach_kernel_driver(self.interface)
                    finally:
                        usb.util.dispose_resources(device)
        finally:
            if self._leased:
                self.lease.release(self.resource, self.owner)
                self._leased = False
