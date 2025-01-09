import asyncio
import json
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from channels.layers import get_channel_layer
import redis
from django.conf import settings
from sat_toolkit.tools.xlogger import xlog
from queue import Queue

logger = xlog.get_logger(__name__)  

class StreamType(Enum):
    UART = "uart"
    CAN = "can"
    SPI = "spi"
    I2C = "i2c"
    CUSTOM = "custom"

class StreamSource(Enum):
    CLIENT = "client"    # Data/commands from client to server
    SERVER = "server"    # Data/responses from server to client
    SYSTEM = "system"    # System events, status updates, etc.

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

    def to_dict(self):
        return {
            "stream_type": self.stream_type.value,
            "channel": self.channel,
            "timestamp": self.timestamp,
            "source": self.source.value,
            "action": self.action.value,
            "data": self.data,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data_dict):
        return cls(
            stream_type=StreamType(data_dict["stream_type"]),
            channel=data_dict["channel"],
            timestamp=data_dict["timestamp"],
            source=StreamSource(data_dict["source"]),
            action=StreamAction(data_dict["action"]),
            data=data_dict["data"],
            metadata=data_dict.get("metadata")
        )

class StreamWrapper:
    """Wrapper class to handle async operations for stream management"""
    def __init__(self, stream_manager):
        self.stream_manager = stream_manager

    def _get_or_create_loop(self):
        """Get existing loop or create new one if needed"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If there's no loop in the current thread, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    def register_stream(self, channel):
        """Synchronous wrapper for registering a stream"""
        loop = self._get_or_create_loop()
        try:
            if loop.is_running():
                return loop.create_task(self.stream_manager.register_stream(channel))
            else:
                return loop.run_until_complete(self.stream_manager.register_stream(channel))
        except Exception as e:
            logger.error(f"Error in register_stream: {e}")
            raise

    def unregister_stream(self, channel):
        """Synchronous wrapper for unregistering a stream"""
        loop = self._get_or_create_loop()
        try:
            if loop.is_running():
                return loop.create_task(self.stream_manager.unregister_stream(channel))
            else:
                return loop.run_until_complete(self.stream_manager.unregister_stream(channel))
        except Exception as e:
            logger.error(f"Error in unregister_stream: {e}")
            raise

    def stop_broadcast(self, channel):
        """Synchronous wrapper for stopping broadcast"""
        loop = self._get_or_create_loop()
        try:
            if loop.is_running():
                return loop.create_task(self.stream_manager.stop_broadcast(channel))
            else:
                return loop.run_until_complete(self.stream_manager.stop_broadcast(channel))
        except Exception as e:
            logger.error(f"Error in stop_broadcast: {e}")
            raise

    def broadcast_data(self, stream_data):
        """Synchronous wrapper for broadcasting data"""
        loop = self._get_or_create_loop()
        try:
            if loop.is_running():
                return loop.create_task(self.stream_manager.broadcast_data(stream_data))
            else:
                return loop.run_until_complete(self.stream_manager.broadcast_data(stream_data))
        except Exception as e:
            logger.error(f"Error in broadcast_data: {e}")
            raise

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
            self._redis = redis.Redis(
                host=getattr(settings, 'REDIS_HOST', 'localhost'),
                port=getattr(settings, 'REDIS_PORT', 6379),
                db=getattr(settings, 'REDIS_DB', 0)
            )
            # 为每个channel创建一个队列来存储客户端数据
            self._client_queues = {}
            self.initialized = True

    async def register_stream(self, channel: str):
        """Register a channel when a client connects"""
        self._redis.sadd('active_channels', channel)
        # 为新channel创建队列
        if channel not in self._client_queues:
            self._client_queues[channel] = Queue()
        logger.info(f"Registered stream for channel {channel}")

    async def unregister_stream(self, channel: str):
        """Unregister a channel when a client disconnects"""
        self._redis.srem('active_channels', channel)
        # 移除channel的队列
        self._client_queues.pop(channel, None)
        logger.info(f"Unregistered stream for channel {channel}")

    async def broadcast_data(self, stream_data: StreamData):
        """Broadcast data and track channels"""
        logger.debug(f"Broadcasting data: {stream_data}")

        channel = stream_data.channel
        
        # 如果是客户端发来的数据，存入对应的队列
        if stream_data.source == StreamSource.CLIENT:
            if channel in self._client_queues:
                self._client_queues[channel].put(stream_data)
                logger.debug(f"Queued client data for channel {channel}")
            return

        # 服务器发往客户端的数据通过WebSocket广播
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

    def get_client_data(self) -> Optional[StreamData]:
        """获取来自客户端的数据"""
        # 检查所有活跃channel的队列
        for channel in self._client_queues:
            queue = self._client_queues[channel]
            if not queue.empty():
                return queue.get_nowait()
        return None