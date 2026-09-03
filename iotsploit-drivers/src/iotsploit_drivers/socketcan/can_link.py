"""What the kernel says about a CAN interface.

This driver used to assume 500 kbit for every interface it discovered, and then
apply that assumption with ``ip link set ... type can bitrate 500000``. On a bus
the operator had already configured -- CAN FD, or any bitrate that is not 500k
-- that replaced a working configuration with a wrong one, and the controller
then piled up receive errors against traffic it could no longer read.

So: ask, do not assume. ``ip -details link show`` already reports the bitrate,
the data bitrate, the MTU that tells FD from classic, and the controller state.
Parsing is kept separate from running the command so it can be tested against
recorded output instead of hardware.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from iotsploit_core.core.tool_manager import PathResolver

logger = logging.getLogger(__name__)

#: A CAN FD interface has an MTU of 72 (``struct canfd_frame``); classic CAN is
#: 16 (``struct can_frame``). This is how the kernel says "FD is enabled here".
CANFD_MTU = 72

_HEADER = re.compile(r"^\d+:\s+(?P<name>[^:@]+)[:@]")
_FLAGS = re.compile(r"<(?P<flags>[^>]*)>")
_MTU = re.compile(r"\bmtu\s+(?P<mtu>\d+)")
# \b stops this matching the "bitrate" inside "dbitrate".
_BITRATE = re.compile(r"\bbitrate\s+(?P<bitrate>\d+)")
_DBITRATE = re.compile(r"\bdbitrate\s+(?P<dbitrate>\d+)")
_CAN_STATE = re.compile(r"^can\b.*?\bstate\s+(?P<state>\S+)")


@dataclass(frozen=True)
class CanLinkInfo:
    """One CAN interface as the kernel currently has it configured."""

    name: str
    is_up: bool
    mtu: Optional[int] = None
    bitrate: Optional[int] = None
    dbitrate: Optional[int] = None
    controller_state: Optional[str] = None
    is_virtual: bool = False

    @property
    def supports_fd(self) -> bool:
        return self.mtu == CANFD_MTU

    def describe(self) -> str:
        """One line for a log or an error message."""
        parts = [self.name, "up" if self.is_up else "down"]
        if self.bitrate:
            parts.append(f"{self.bitrate} bit/s")
        if self.dbitrate:
            parts.append(f"data {self.dbitrate} bit/s")
        parts.append("FD" if self.supports_fd else "classic")
        if self.controller_state:
            parts.append(self.controller_state)
        return ", ".join(parts)


def parse_ip_link_details(text: str) -> Dict[str, CanLinkInfo]:
    """Index ``ip -details link show`` output by interface name.

    Only interfaces whose block declares ``link/can`` are returned: matching on
    the substring "can" alone, as this driver used to, also matches an ethernet
    device that happens to be named for a canyon.
    """
    links: Dict[str, CanLinkInfo] = {}

    for block in _blocks(text):
        header, rest = block[0], block[1:]
        match = _HEADER.match(header)
        if not match:
            continue
        body = "\n".join(rest)
        if "link/can" not in body:
            continue

        name = match.group("name").strip()
        flags = _FLAGS.search(header)
        mtu = _MTU.search(header)
        bitrate = _BITRATE.search(body)
        dbitrate = _DBITRATE.search(body)

        state = None
        for line in rest:
            can_state = _CAN_STATE.match(line.strip())
            if can_state:
                state = can_state.group("state")
                break

        links[name] = CanLinkInfo(
            name=name,
            # The flag list is admin state, which is what "can I open a socket
            # on this" depends on. `state UP` in the same line is operational.
            is_up="UP" in (flags.group("flags").split(",") if flags else []),
            mtu=int(mtu.group("mtu")) if mtu else None,
            bitrate=int(bitrate.group("bitrate")) if bitrate else None,
            dbitrate=int(dbitrate.group("dbitrate")) if dbitrate else None,
            controller_state=state,
            is_virtual=name.startswith("vcan") or name.startswith("vxcan"),
        )

    return links


def _blocks(text: str):
    """Group output lines by interface: a header line and its indented rest."""
    block = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace() and block:
            yield block
            block = []
        block.append(line)
    if block:
        yield block


def read_can_links(runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Dict[str, CanLinkInfo]:
    """Every CAN interface on this host, or an empty mapping if ip(8) fails.

    ``runner`` is injected so tests can supply recorded output; nothing here
    touches a device.
    """
    try:
        executable = PathResolver().resolve_tool_path("ip")
        if not executable:
            raise FileNotFoundError("ip")
        result = runner(
            [executable, "-details", "link", "show"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("Could not list network interfaces: %s", exc)
        return {}

    if result.returncode != 0:
        logger.error("ip link show failed (%s): %s", result.returncode, (result.stderr or "").strip())
        return {}

    return parse_ip_link_details(result.stdout or "")
