import abc
from typing import Any, Optional


class HWInterface(abc.ABC):
    """Abstract hardware interface."""

    @abc.abstractmethod
    def send(self, data: bytes) -> None:
        ...

    @abc.abstractmethod
    def receive(self, timeout: float = 0.1) -> Optional[bytes]:
        ...

    def close(self) -> None:
        pass 