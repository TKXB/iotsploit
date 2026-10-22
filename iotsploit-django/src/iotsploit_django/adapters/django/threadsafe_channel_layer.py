"""In-memory channel layer that owns all state on one ASGI event loop."""

from __future__ import annotations

import asyncio
import contextvars
import threading

from asgiref.sync import async_to_sync
from channels.layers import InMemoryChannelLayer


class ThreadSafeInMemoryChannelLayer(InMemoryChannelLayer):
    """Marshal worker-thread group sends onto the consumer event loop."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._asgi_loop = None
        self._loop_lock = threading.Lock()

    def _capture_loop(self):
        loop = asyncio.get_running_loop()
        if self._asgi_loop is None:
            with self._loop_lock:
                if self._asgi_loop is None:
                    self._asgi_loop = loop
        return loop

    async def new_channel(self, prefix="specific."):
        self._capture_loop()
        return await super().new_channel(prefix)

    async def receive(self, channel):
        self._capture_loop()
        return await super().receive(channel)

    async def group_add(self, group, channel):
        self._capture_loop()
        return await super().group_add(group, channel)

    async def group_discard(self, group, channel):
        self._capture_loop()
        return await super().group_discard(group, channel)

    async def group_send(self, group, message):
        current_loop = asyncio.get_running_loop()
        home_loop = self._asgi_loop
        if home_loop is None or home_loop is current_loop:
            return await super().group_send(group, message)

        self.group_send_threadsafe(group, message)

    def group_send_threadsafe(self, group, message):
        """Queue a send from synchronous worker code onto the ASGI loop."""
        home_loop = self._asgi_loop
        if home_loop is None:
            async_to_sync(InMemoryChannelLayer.group_send)(self, group, message)
            return
        home_loop.call_soon_threadsafe(
            self._send_on_home_loop,
            group,
            message,
            context=contextvars.Context(),
        )

    def _send_on_home_loop(self, group, message):
        self._asgi_loop.create_task(InMemoryChannelLayer.group_send(self, group, message))


def send_group(channel_layer, group, message):
    """Send from synchronous code through either local or distributed Channels."""
    local_send = getattr(channel_layer, "group_send_threadsafe", None)
    if local_send is not None:
        local_send(group, message)
    else:
        async_to_sync(channel_layer.group_send)(group, message)
