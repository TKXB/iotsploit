from __future__ import annotations

import asyncio
from queue import Queue
import threading
from typing import Dict, Optional

from channels.layers import get_channel_layer
from django.conf import settings

from iotsploit_core.domain.stream import StreamData, StreamSource
from iotsploit_django.tools.xlogger import xlog

logger = xlog.get_logger(__name__)


class DjangoStreamManager:
    """Channels-backed StreamManager with mode-specific shared tracking.

    This implementation requires Django settings and `channels` to be configured.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.channel_layer = get_channel_layer()
            self._distributed = settings.IOTSPLOIT_RUNTIME == "distributed"
            if self._distributed:
                import redis

                self._redis = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                )
            else:
                self._active_channels = set()
                self._broadcast_channels = set()
                self._state_lock = threading.Lock()
            self._client_queues: Dict[str, Queue] = {}
            self.initialized = True

    async def register_stream(self, channel: str):
        if self._distributed:
            self._redis.sadd("active_channels", channel)
        else:
            with self._state_lock:
                self._active_channels.add(channel)
        if channel not in self._client_queues:
            self._client_queues[channel] = Queue()
        logger.info(f"Registered stream for channel {channel}")

    async def unregister_stream(self, channel: str):
        if self._distributed:
            self._redis.srem("active_channels", channel)
        else:
            with self._state_lock:
                self._active_channels.discard(channel)
        self._client_queues.pop(channel, None)
        logger.info(f"Unregistered stream for channel {channel}")

    async def broadcast_data(self, stream_data: StreamData):
        channel = stream_data.channel

        # Client -> server: enqueue only
        if stream_data.source == StreamSource.CLIENT:
            if channel in self._client_queues:
                self._client_queues[channel].put(stream_data)
            return

        # Server -> client: broadcast via Channels
        if self._distributed:
            self._redis.sadd("broadcast_channels", channel)
        else:
            with self._state_lock:
                self._broadcast_channels.add(channel)
        group_name = f"stream_{channel}"
        message = {"type": "stream_data", "data": stream_data.to_dict()}

        try:
            await self.channel_layer.group_send(group_name, message)
        except Exception as e:
            logger.error(f"Error broadcasting to group {group_name}: {str(e)}")

    async def stop_broadcast(self, channel: str):
        if self._distributed:
            self._redis.srem("broadcast_channels", channel)
        else:
            with self._state_lock:
                self._broadcast_channels.discard(channel)
        logger.info(f"Stopped broadcasting on channel {channel}")

    def get_active_channels(self):
        if self._distributed:
            return [channel.decode() for channel in self._redis.smembers("active_channels")]
        with self._state_lock:
            return list(self._active_channels)

    def get_broadcast_channels(self):
        if self._distributed:
            return [channel.decode() for channel in self._redis.smembers("broadcast_channels")]
        with self._state_lock:
            return list(self._broadcast_channels)

    def get_client_data(self) -> Optional[StreamData]:
        for channel in self._client_queues:
            q = self._client_queues[channel]
            if not q.empty():
                return q.get_nowait()
        return None


# Backward-compatible alias: in this refactor, core expects an injected backend.
# This adapter class already satisfies the StreamBackend Protocol.
DjangoStreamBackend = DjangoStreamManager


class StreamWrapper:
    """Wrapper class to handle async operations for stream management (adapter layer)."""

    def __init__(self, stream_manager):
        self.stream_manager = stream_manager

    def _get_or_create_loop(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    def register_stream(self, channel):
        loop = self._get_or_create_loop()
        if loop.is_running():
            return loop.create_task(self.stream_manager.register_stream(channel))
        return loop.run_until_complete(self.stream_manager.register_stream(channel))

    def unregister_stream(self, channel):
        loop = self._get_or_create_loop()
        if loop.is_running():
            return loop.create_task(self.stream_manager.unregister_stream(channel))
        return loop.run_until_complete(self.stream_manager.unregister_stream(channel))

    def stop_broadcast(self, channel):
        loop = self._get_or_create_loop()
        if loop.is_running():
            return loop.create_task(self.stream_manager.stop_broadcast(channel))
        return loop.run_until_complete(self.stream_manager.stop_broadcast(channel))

    def broadcast_data(self, stream_data):
        loop = self._get_or_create_loop()
        if loop.is_running():
            return loop.create_task(self.stream_manager.broadcast_data(stream_data))
        return loop.run_until_complete(self.stream_manager.broadcast_data(stream_data))
