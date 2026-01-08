from typing import Optional

from .base import HWInterface

try:
    import spidev  # type: ignore
except ImportError:
    spidev = None


class SPIInterface(HWInterface):
    def __init__(self, bus: int = 0, device: int = 0, max_speed_hz: int = 500000):
        if spidev is None:
            raise RuntimeError("spidev not installed. Install via pip install spidev (Linux only)")
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = max_speed_hz

    def send(self, data: bytes) -> None:
        self.spi.xfer2(list(data))

    def receive(self, timeout: float = 0.1) -> Optional[bytes]:
        # SPI is synchronous; separate receive not always meaningful.
        return None

    def close(self) -> None:
        self.spi.close() 