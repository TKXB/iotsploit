import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from channels.layers import get_channel_layer
import redis
from django.conf import settings

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
    _redis = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.channel_layer = get_channel_layer()
            # Initialize Redis connection
            self._redis = redis.Redis(
                host=getattr(settings, 'REDIS_HOST', 'localhost'),
                port=getattr(settings, 'REDIS_PORT', 6379),
                db=getattr(settings, 'REDIS_DB', 0)
            )
            self.initialized = True

    async def register_stream(self, channel: str):
        """Register a channel when a client connects"""
        self._redis.sadd('active_channels', channel)
        logger.info(f"Registered stream for channel {channel}")

    async def unregister_stream(self, channel: str):
        """Unregister a channel when a client disconnects"""
        self._redis.srem('active_channels', channel)
        logger.info(f"Unregistered stream for channel {channel}")

    async def broadcast_data(self, stream_data: StreamData):
        """Broadcast data and track channels"""
        logger.debug(f"Broadcasting data: {stream_data}")

        channel = stream_data.channel
        self._redis.sadd('broadcast_channels', channel)
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
        self._redis.srem('broadcast_channels', channel)
        logger.info(f"Stopped broadcasting on channel {channel}")

    def get_active_channels(self):
        """Get channels with connected clients"""
        return [channel.decode() for channel in self._redis.smembers('active_channels')]

    def get_broadcast_channels(self):
        """Get channels where data is being broadcast"""
        return [channel.decode() for channel in self._redis.smembers('broadcast_channels')]