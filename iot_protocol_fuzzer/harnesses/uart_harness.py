from typing import Optional

from .base import ProtocolHarness, HarnessResult
from ..interfaces.uart_interface import UARTInterface


class UARTHarness(ProtocolHarness):
    def __init__(self, interface: Optional[UARTInterface] = None):
        self.iface = interface or UARTInterface()

    def execute(self, payload: bytes) -> HarnessResult:
        try:
            self.iface.send(payload)
            response = self.iface.receive()
            
            # Check if response is None (timeout) or empty bytes (no data)
            if response is None:
                return HarnessResult(ok=True, timeout=True, response=None)
            else:
                return HarnessResult(ok=True, response=response)
                
        except Exception as exc:
            return HarnessResult(ok=False, crashed=True, info=str(exc), error=str(exc)) 