from typing import Optional

from .base import HWInterface

try:
    import can  # type: ignore
except ImportError:  # pragma: no cover
    can = None


class SocketCANInterface(HWInterface):
    """Very thin wrapper around python-can.
    If python-can is not installed, this interface will raise.
    """

    def __init__(self, channel: str = "can0", bitrate: int = 500000):
        if can is None:
            raise RuntimeError("python-can not installed. Install via pip install python-can")
        self.bus = can.interface.Bus(channel=channel, bustype="socketcan", bitrate=bitrate)

    def send(self, data: bytes) -> None:
        # Split data into 8-byte CAN frames (standard data frame)
        from can import Message

        for idx in range(0, len(data), 8):
            chunk = data[idx : idx + 8]
            msg = Message(arbitration_id=0x123, data=list(chunk), is_extended_id=False)
            self.bus.send(msg)

    def receive(self, timeout: float = 0.1) -> Optional[bytes]:
        msg = self.bus.recv(timeout)
        if msg:
            return bytes(msg.data)
        return None

    def close(self) -> None:
        self.bus.shutdown() 