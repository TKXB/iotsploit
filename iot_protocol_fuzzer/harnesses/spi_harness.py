from typing import Optional

from .base import ProtocolHarness, HarnessResult
from ..interfaces.spi_interface import SPIInterface


class SPIHarness(ProtocolHarness):
    def __init__(self, interface: Optional[SPIInterface] = None):
        self.iface = interface or SPIInterface()

    def execute(self, payload: bytes) -> HarnessResult:
        try:
            self.iface.send(payload)
            # For SPI synchronous send/receive we ignore response for now.
            return HarnessResult(ok=True)
        except Exception as exc:
            return HarnessResult(ok=False, crashed=True, info=str(exc), error=str(exc)) 