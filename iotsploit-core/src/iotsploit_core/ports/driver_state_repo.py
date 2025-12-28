from __future__ import annotations

from typing import Protocol


class DriverStateRepository(Protocol):
    """Persistence port for driver enable/disable states."""

    def get_enabled(self, driver_name: str) -> bool | None: ...

    def set_enabled(self, driver_name: str, enabled: bool, description: str | None = None) -> None: ...

    def list_enabled(self) -> dict[str, bool]: ...


