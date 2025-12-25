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
from sat_toolkit.ports.stream_backend import StreamBackend
import logging

logger = logging.getLogger(__name__)


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


class _NoopStreamBackend:
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
    """Core stream manager that delegates to an injected backend.

    Default backend is a Noop implementation. Django wiring should inject a real backend
    during app startup (composition root).
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_backend"):
            return
        self._backend: StreamBackend = _NoopStreamBackend()

    @classmethod
    def configure_backend(cls, backend: StreamBackend) -> None:
        """Wire a backend implementation (to be called from Django wiring)."""

        inst = cls()
        inst._backend = backend

    # Delegate API
    async def register_stream(self, channel: str):
        return await self._backend.register_stream(channel)

    async def unregister_stream(self, channel: str):
        return await self._backend.unregister_stream(channel)

    async def broadcast_data(self, stream_data: StreamData):
        return await self._backend.broadcast_data(stream_data)

    async def stop_broadcast(self, channel: str):
        return await self._backend.stop_broadcast(channel)

    def get_active_channels(self):
        return self._backend.get_active_channels()

    def get_broadcast_channels(self):
        return self._backend.get_broadcast_channels()

    def get_client_data(self) -> Optional[StreamData]:
        return self._backend.get_client_data()