from __future__ import annotations

from typing import Protocol

from sat_toolkit.domain.stream import StreamData


class StreamBackend(Protocol):
    """Streaming backend port.

    Core code should depend on this Protocol, not on Django/Channels/Redis implementations.
    """

    async def register_stream(self, channel: str) -> None: ...

    async def unregister_stream(self, channel: str) -> None: ...

    async def broadcast_data(self, stream_data: StreamData) -> None: ...

    async def stop_broadcast(self, channel: str) -> None: ...

    def get_active_channels(self) -> list[str]: ...

    def get_broadcast_channels(self) -> list[str]: ...

    def get_client_data(self) -> StreamData | None: ...


