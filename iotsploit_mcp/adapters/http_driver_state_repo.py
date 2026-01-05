from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class DjangoHttpApiConfig:
    base_url: str
    timeout_s: float = 5.0
    bearer_token: str | None = None


class HttpDriverStateRepository:
    """DriverStateRepository over iotsploit_django HTTP API.

    Django endpoints (mounted under `/api/`):
    - GET  /api/get_driver_states/
    - POST /api/enable_driver/
    - POST /api/disable_driver/
    """

    def __init__(self, *, base_url: str, timeout_s: float = 5.0, bearer_token: str | None = None) -> None:
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required for HttpDriverStateRepository")
        self._cfg = DjangoHttpApiConfig(base_url=base_url, timeout_s=float(timeout_s), bearer_token=bearer_token)
        self._session = requests.Session()

    @staticmethod
    def from_env() -> "HttpDriverStateRepository":
        # `django_commands.py` uses http://localhost:8888 for Django HTTP API by default.
        base_url = os.getenv("IOTSPLOIT_DJANGO_API_BASE_URL", "http://127.0.0.1:8888")
        timeout_s = float(os.getenv("IOTSPLOIT_DJANGO_API_TIMEOUT_S", "5.0"))
        bearer_token = os.getenv("IOTSPLOIT_DJANGO_API_TOKEN") or None
        return HttpDriverStateRepository(base_url=base_url, timeout_s=timeout_s, bearer_token=bearer_token)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._cfg.bearer_token:
            headers["Authorization"] = f"Bearer {self._cfg.bearer_token}"
        return headers

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self._cfg.base_url}{path}"

    @staticmethod
    def _raise_for_bad_response(resp: requests.Response, *, context: str) -> None:
        if 200 <= resp.status_code < 300:
            return
        raise RuntimeError(f"{context} failed: HTTP {resp.status_code}: {resp.text[:500]}")

    def list_enabled(self) -> dict[str, bool]:
        resp = self._session.get(
            self._url("/api/get_driver_states/"),
            headers=self._headers(),
            timeout=self._cfg.timeout_s,
        )
        self._raise_for_bad_response(resp, context="GET /api/get_driver_states/")

        payload: dict[str, Any] = resp.json()
        if payload.get("status") not in (None, "success"):
            raise RuntimeError(f"GET /api/get_driver_states/ returned error: {payload!r}")

        drivers = payload.get("drivers") or {}
        if not isinstance(drivers, dict):
            raise RuntimeError(f"Unexpected drivers payload: {drivers!r}")

        out: dict[str, bool] = {}
        for name, state in drivers.items():
            if isinstance(state, dict):
                out[str(name)] = bool(state.get("enabled", True))
            else:
                out[str(name)] = bool(state)
        return out

    def get_enabled(self, driver_name: str) -> bool | None:
        if not driver_name:
            return None
        states = self.list_enabled()
        return states.get(driver_name)

    def set_enabled(self, driver_name: str, enabled: bool, description: str | None = None) -> None:
        if not driver_name:
            raise ValueError("driver_name is required")

        endpoint = "/api/enable_driver/" if enabled else "/api/disable_driver/"
        body: dict[str, Any] = {"driver_name": driver_name}
        if description is not None:
            body["description"] = description

        resp = self._session.post(
            self._url(endpoint),
            headers={**self._headers(), "Content-Type": "application/json"},
            json=body,
            timeout=self._cfg.timeout_s,
        )
        self._raise_for_bad_response(resp, context=f"POST {endpoint}")

        payload: dict[str, Any] = resp.json()
        if payload.get("status") not in (None, "success"):
            raise RuntimeError(f"POST {endpoint} returned error: {payload!r}")


