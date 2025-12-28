from __future__ import annotations


class MemoryDriverStateRepository:
    def __init__(self) -> None:
        self._enabled: dict[str, bool] = {}
        self._description: dict[str, str | None] = {}

    def get_enabled(self, driver_name: str) -> bool | None:
        return self._enabled.get(driver_name)

    def set_enabled(self, driver_name: str, enabled: bool, description: str | None = None) -> None:
        self._enabled[driver_name] = bool(enabled)
        if description is not None:
            self._description[driver_name] = description

    def list_enabled(self) -> dict[str, bool]:
        return dict(self._enabled)


