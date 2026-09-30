from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pyocd.core.session import Session
from pyocd.core.target import Target
from pyocd.probe.stlink_probe import StlinkProbe

from iotsploit_core.core.base_plugin import BaseDeviceDriver
from iotsploit_core.domain.device import Device, DeviceType
from iotsploit_core.domain.monitoring import usb_resource

logger = logging.getLogger(__name__)

STMICRO_USB_VENDOR_ID = 0x0483


class STLinkDriver(BaseDeviceDriver):
    """Device driver for ST-LINK debug probes, through pyOCD.

    Also a ``DebugAccess`` backend: target monitors use it as a plain transport
    and do all decoding in ``iotsploit_core.core.monitoring.arch``.

    pyOCD refuses ST-LINK/V2 firmware older than V2J24; update the probe with
    ST's STLinkUpgrade. The session uses pyOCD's generic ``cortex_m`` target: a
    monitor never programs flash, so it needs no device pack, and it checks the
    CPUID against the target profile itself.
    """

    REQUIRES = ("module:pyocd",)
    DEBUG_USB_VENDOR_IDS = (STMICRO_USB_VENDOR_ID,)

    def __init__(self):
        super().__init__()
        self.session: Optional[Session] = None

    # ------------------------------------------------------------------
    # BaseDeviceDriver implementation
    # ------------------------------------------------------------------

    def _scan_impl(self) -> List[Device]:
        devices = []
        for probe in StlinkProbe.get_all_connected_probes():
            sn = probe.unique_id
            devices.append(Device(
                device_id=f"stlink_{sn}",
                name=f"{probe.product_name} ({sn})",
                device_type=DeviceType.USB,
                attributes={"probe_sn": sn, "product": probe.product_name},
            ))
            logger.info("Found ST-LINK probe: SN=%s", sn)
        return devices

    def _initialize_impl(self, device: Device) -> bool:
        serial = device.attributes.get("probe_sn")
        if not serial:
            raise ValueError("Device is missing 'probe_sn' attribute")
        probe = StlinkProbe.get_probe_with_id(serial)
        if probe is None:
            raise RuntimeError(f"ST-LINK {serial} is not connected")
        session = Session(probe, target_override="cortex_m", connect_mode="attach",
                          dap_protocol=device.attributes.get("interface", "swd"))
        try:
            session.open()
        except Exception as exc:
            session.close()
            raise RuntimeError(f"Cannot open ST-LINK {serial}: {exc}") from exc
        self.session = session
        logger.info("ST-LINK initialized: %s", device.name)
        return True

    def _connect_impl(self, device: Device) -> bool:
        if self.session is None:
            raise RuntimeError("ST-LINK not initialised – call initialize first")
        return self.session.is_open

    def _command_impl(self, device: Device, command: str, args: Optional[Dict] = None) -> Any:
        raise ValueError(f"Unsupported command: {command}")

    def resource_key(self, device: Device) -> Optional[str]:
        serial = device.attributes.get("probe_sn")
        return usb_resource(STMICRO_USB_VENDOR_ID, serial, "debug") if serial else None

    # ------------------------------------------------------------------
    # DebugAccess (iotsploit_core.ports.debug_access)
    # ------------------------------------------------------------------

    def debug_architectures(self) -> frozenset[str]:
        return frozenset({"cortex_m"})

    def attach(self, serial: str, target: str, *, interface: str = "swd") -> None:
        device = Device(
            device_id=f"stlink_{serial}",
            name=f"ST-LINK {serial}",
            device_type=DeviceType.USB,
            attributes={"probe_sn": serial, "interface": interface},
        )
        self.initialize(device)
        self.device = device

    def detach(self) -> None:
        session, self.session = self.session, None
        if session is not None:
            session.close()

    def read_mem32(self, address: int, count: int = 1) -> list[int]:
        return list(self._target().read_memory_block32(address, count))

    def read_registers(self, names) -> list[int]:
        # pyOCD spells Cortex-M registers the canonical way already.
        return list(self._target().read_core_registers_raw(list(names)))

    def halt(self) -> None:
        self._target().halt()

    def is_halted(self) -> bool:
        return self._target().get_state() == Target.State.HALTED

    def resume(self) -> None:
        self._target().resume()

    def reset_core(self, *, halt: bool = False) -> None:
        # pyOCD polls DHCSR while resetting, so its own reset leaves no
        # S_RESET_ST for the next sample; a reset the target makes still does.
        if halt:
            self._target().reset_and_halt()
        else:
            self._target().reset()

    def _target(self):
        if self.session is None:
            raise RuntimeError("ST-LINK is not initialized")
        return self.session.board.target

    def _reset_impl(self, device: Device) -> bool:
        if self.session is None:
            return False
        self.session.board.target.reset()
        return True

    def _close_impl(self, device: Device) -> bool:
        self.detach()
        return True

    def _recovery_impl(self, device: Device, recovery_type: str, **kwargs) -> dict:
        raise NotImplementedError("Recovery operations not implemented for ST-LINK driver")

    def _get_supported_recovery_operations_impl(self) -> list:
        return []
