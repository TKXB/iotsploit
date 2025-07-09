from typing import Optional

from .base import ProtocolHarness, HarnessResult
from ..interfaces.can_interface import SocketCANInterface


class CANHarness(ProtocolHarness):
    def __init__(self, interface: Optional[SocketCANInterface] = None):
        self.iface = interface or SocketCANInterface()

    def execute(self, payload: bytes) -> HarnessResult:
        try:
            self.iface.send(payload)
            response = self.iface.receive()
            
            # Check if response is None (timeout) or has data
            if response is None:
                return HarnessResult(ok=True, timeout=True, response=None)
            else:
                return HarnessResult(ok=True, response=response)
                
        except Exception as exc:
            return HarnessResult(ok=False, crashed=True, info=str(exc), error=str(exc)) 