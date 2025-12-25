from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class StreamType(Enum):
    UART = "uart"
    CAN = "can"
    SPI = "spi"
    I2C = "i2c"
    CUSTOM = "custom"


class StreamSource(Enum):
    CLIENT = "client"  # Data/commands from client to server
    SERVER = "server"  # Data/responses from server to client
    SYSTEM = "system"  # System events, status updates, etc.


class StreamAction(Enum):
    DATA = "data"  # Regular data transmission/reception
    SEND = "send"  # Request to send data
    CONFIG = "config"  # Configuration changes
    STATUS = "status"  # Status updates
    ERROR = "error"  # Error notifications


@dataclass
class StreamData:
    stream_type: StreamType
    channel: str
    timestamp: float
    source: StreamSource
    action: StreamAction
    data: Any
    metadata: Optional[Dict] = None

    def to_dict(self) -> dict:
        return {
            "stream_type": self.stream_type.value,
            "channel": self.channel,
            "timestamp": self.timestamp,
            "source": self.source.value,
            "action": self.action.value,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data_dict: dict) -> "StreamData":
        return cls(
            stream_type=StreamType(data_dict["stream_type"]),
            channel=data_dict["channel"],
            timestamp=data_dict["timestamp"],
            source=StreamSource(data_dict["source"]),
            action=StreamAction(data_dict["action"]),
            data=data_dict["data"],
            metadata=data_dict.get("metadata"),
        )


