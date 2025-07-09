from typing import Optional

from .base import HWInterface

try:
    import serial  # type: ignore
except ImportError:
    serial = None


class UARTInterface(HWInterface):
    def __init__(self, device: str = "/dev/ttyUSB0", baudrate: int = 115200, timeout: float = 0.1):
        if serial is None:
            raise RuntimeError("pyserial not installed. Install via pip install pyserial")
        self.ser = serial.Serial(device, baudrate=baudrate, timeout=timeout)

    def send(self, data: bytes) -> None:
        self.ser.write(data)

    def receive(self, timeout: float = 0.1) -> Optional[bytes]:
        self.ser.timeout = timeout
        data = self.ser.read(1024)
        return data if data else None

    def close(self) -> None:
        self.ser.close() 