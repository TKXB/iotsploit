import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

class StreamType(Enum):
    UART = "uart"
    CAN = "can"
    SPI = "spi"
    I2C = "i2c"
    CUSTOM = "custom"

@dataclass
class StreamData:
    stream_type: StreamType
    channel: str
    timestamp: float
    data: Any
    metadata: Optional[Dict] = None

    def to_dict(self):
        return {
            "stream_type": self.stream_type.value,
            "channel": self.channel,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata
        }

class StreamManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.channel_layer = get_channel_layer()
            self.initialized = True

    async def register_stream(self, channel: str, channel_name: str):
        """Register a WebSocket channel for a data stream"""
        if channel not in self.active_streams:
            self.active_streams[channel] = set()
        self.active_streams[channel].add(channel_name)
        logger.info(f"Registered stream for channel {channel} on channel {channel_name}")

    async def unregister_stream(self, channel: str, channel_name: str):
        """Unregister a WebSocket channel from a data stream"""
        if channel in self.active_streams:
            self.active_streams[channel].discard(channel_name)
            if not self.active_streams[channel]:
                del self.active_streams[channel]
        logger.info(f"Unregistered stream for channel {channel} from channel {channel_name}")

    async def broadcast_data(self, stream_data: StreamData):
        """Broadcast data to all registered channels for a stream"""
        logger.debug(f"Broadcasting data: {stream_data}")

        channel = stream_data.channel
        group_name = f"stream_{channel}"
        
        message = {
            "type": "stream_data",
            "data": stream_data.to_dict()
        }
        
        logger.debug(f"Broadcasting message to group {group_name}")

        try:
            await self.channel_layer.group_send(group_name, message)
        except Exception as e:
            logger.error(f"Error broadcasting to group {group_name}: {str(e)}")