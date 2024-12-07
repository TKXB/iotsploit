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
            self.active_channels = set()  # Channels with connected clients
            self.broadcast_channels = set()  # Channels where data is being broadcast
            self.initialized = True

    async def register_stream(self, channel: str):
        """Register a channel when a client connects"""
        self.active_channels.add(channel)
        logger.info(f"Registered stream for channel {channel}")

    async def unregister_stream(self, channel: str):
        """Unregister a channel when a client disconnects"""
        self.active_channels.discard(channel)
        logger.info(f"Unregistered stream for channel {channel}")

    async def broadcast_data(self, stream_data: StreamData):
        """Broadcast data and track channels"""
        logger.debug(f"Broadcasting data: {stream_data}")

        channel = stream_data.channel
        self.broadcast_channels.add(channel)  # Track broadcasting channels
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

    async def stop_broadcast(self, channel: str):
        """Stop broadcasting on a channel"""
        self.broadcast_channels.discard(channel)
        logger.info(f"Stopped broadcasting on channel {channel}")

    def get_active_channels(self):
        """Get channels with connected clients"""
        return list(self.active_channels)

    def get_broadcast_channels(self):
        """Get channels where data is being broadcast"""
        return list(self.broadcast_channels)