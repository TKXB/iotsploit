from __future__ import annotations

"""Core stream facade (no Django/Channels hard dependency).

This module intentionally avoids importing Django/Channels/Redis at import time, so that
`sat_toolkit.core` can be imported in standalone contexts. In a Django runtime, it will
try to delegate to the adapter implementation.
"""

import asyncio
from queue import Queue
from typing import Dict, Optional

from sat_toolkit.domain.stream import StreamAction, StreamData, StreamSource, StreamType
from sat_toolkit.tools.xlogger import xlog

logger = xlog.get_logger(__name__)


# Re-export domain stream types for backward compatibility with existing imports.
__all__ = [
    "StreamType",
    "StreamSource",
    "StreamAction",
    "StreamData",
    "StreamWrapper",
    "StreamManager",
]


class StreamWrapper:
    """Wrapper class to handle async operations for stream management."""

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


class _NoopStreamManager:
    """Fallback stream manager when Django/Channels is unavailable.

    Keeps API shape compatible but does not broadcast over WebSocket.
    """

    def __init__(self):
        self._client_queues: Dict[str, Queue] = {}

    async def register_stream(self, channel: str):
        if channel not in self._client_queues:
            self._client_queues[channel] = Queue()

    async def unregister_stream(self, channel: str):
        self._client_queues.pop(channel, None)

    async def broadcast_data(self, stream_data: StreamData):
        # For CLIENT source, enqueue so server-side can consume.
        if stream_data.source == StreamSource.CLIENT:
            q = self._client_queues.get(stream_data.channel)
            if q is not None:
                q.put(stream_data)

    async def stop_broadcast(self, channel: str):
        return

    def get_active_channels(self):
        return list(self._client_queues.keys())

    def get_broadcast_channels(self):
        return []

    def get_client_data(self) -> Optional[StreamData]:
        for ch in list(self._client_queues.keys()):
            q = self._client_queues[ch]
            if not q.empty():
                return q.get_nowait()
        return None


class StreamManager:
    """Facade that delegates to Django adapter when available, else Noop."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_impl"):
            return

        # Lazy import: only in full Django runtime should this succeed.
        try:
            from sat_toolkit.adapters.django.stream_manager import DjangoStreamManager as _DjangoStreamManager

            self._impl = _DjangoStreamManager()
            logger.debug("StreamManager using DjangoStreamManager adapter", name=__name__)
        except Exception:
            self._impl = _NoopStreamManager()
            logger.debug("StreamManager using Noop implementation", name=__name__)

    # Delegate API
    async def register_stream(self, channel: str):
        return await self._impl.register_stream(channel)

    async def unregister_stream(self, channel: str):
        return await self._impl.unregister_stream(channel)

    async def broadcast_data(self, stream_data: StreamData):
        return await self._impl.broadcast_data(stream_data)

    async def stop_broadcast(self, channel: str):
        return await self._impl.stop_broadcast(channel)

    def get_active_channels(self):
        return self._impl.get_active_channels()

    def get_broadcast_channels(self):
        return self._impl.get_broadcast_channels()

    def get_client_data(self) -> Optional[StreamData]:
        return self._impl.get_client_data()