from typing import Optional
import logging

from .base import HWInterface

try:
    import can  # type: ignore
except ImportError:  # pragma: no cover
    can = None

logger = logging.getLogger("can.interface")


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

        logger.debug(f"Sending CAN data: {data.hex()} ({len(data)} bytes)")
        
        for idx in range(0, len(data), 8):
            chunk = data[idx : idx + 8]
            msg = Message(arbitration_id=0x123, data=list(chunk), is_extended_id=False)
            
            # Log each CAN frame being sent
            logger.debug(f"  CAN Frame {idx//8}: ID=0x{msg.arbitration_id:03X}, Data={chunk.hex()}, Length={len(chunk)}")
            
            self.bus.send(msg)

    def receive(self, timeout: float = 0.1) -> Optional[bytes]:
        msg = self.bus.recv(timeout)
        if msg:
            received_data = bytes(msg.data)
            logger.debug(f"Received CAN frame: ID=0x{msg.arbitration_id:03X}, Data={received_data.hex()}")
            return received_data
        return None

    def close(self) -> None:
        self.bus.shutdown() 