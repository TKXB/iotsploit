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
    device_id: str
    timestamp: float
    data: Any
    metadata: Optional[Dict] = None

    def to_dict(self):
        return {
            "stream_type": self.stream_type.value,
            "device_id": self.device_id,
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

    async def register_stream(self, device_id: str, channel_name: str):
        """Register a WebSocket channel for a device's data stream"""
        if device_id not in self.active_streams:
            self.active_streams[device_id] = set()
        self.active_streams[device_id].add(channel_name)
        logger.info(f"Registered stream for device {device_id} on channel {channel_name}")

    async def unregister_stream(self, device_id: str, channel_name: str):
        """Unregister a WebSocket channel from a device's data stream"""
        if device_id in self.active_streams:
            self.active_streams[device_id].discard(channel_name)
            if not self.active_streams[device_id]:
                del self.active_streams[device_id]
        logger.info(f"Unregistered stream for device {device_id} from channel {channel_name}")

    async def broadcast_data(self, stream_data: StreamData):
        """Broadcast data to all registered channels for a device"""
        logger.debug(f"Broadcasting data: {stream_data}")

        device_id = stream_data.device_id
        group_name = f"device_{device_id}"
        
        message = {
            "type": "stream_data",
            "data": stream_data.to_dict()
        }
        
        logger.debug(f"Broadcasting message to group {group_name}")

        try:
            await self.channel_layer.group_send(group_name, message)
        except Exception as e:
            logger.error(f"Error broadcasting to group {group_name}: {str(e)}")