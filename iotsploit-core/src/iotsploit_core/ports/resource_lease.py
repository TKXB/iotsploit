"""Port for exclusive ownership of a piece of hardware.

Two users of one probe or serial port interleave their traffic and corrupt each
other: a campaign's core monitor and a boundary scan on the same J-Link, or a
UART monitor and the terminal page on the same port. Whoever opens a resource
takes its lease first; whoever finds it held gets told who holds it.

Keys are built by ``iotsploit_core.domain.monitoring.usb_resource`` and friends.
The adapter is chosen by the composition root; the Rust boundary-scan bridge
takes the same lock files as the Python adapter.
"""

from __future__ import annotations

from typing import Protocol


class ResourceBusyError(RuntimeError):
    """The resource is leased by someone else."""

    def __init__(self, resource: str, holder: str):
        super().__init__(f"{resource} is in use by {holder}")
        self.resource = resource
        self.holder = holder


class ResourceLeasePort(Protocol):
    def acquire(self, resource: str, owner: str) -> None:
        """Take ``resource`` for ``owner`` or raise :class:`ResourceBusyError`."""
        ...

    def release(self, resource: str, owner: str) -> None:
        """Give ``resource`` back. Releasing a lease not held is a no-op."""
        ...
