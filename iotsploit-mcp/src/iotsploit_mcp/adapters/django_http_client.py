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


class DjangoHttpError(RuntimeError):
    """Raised when the Django API is unreachable or returns a non-2xx response."""

    def __init__(self, message: str, *, status_code: int | None = None, response_text: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class DjangoHttpClient:
    """Small typed client for the IoTSploit Django HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 5.0,
        bearer_token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required for DjangoHttpClient")
        self.config = DjangoHttpApiConfig(
            base_url=base_url,
            timeout_s=float(timeout_s),
            bearer_token=bearer_token,
        )
        self._session = session or requests.Session()

    @staticmethod
    def from_env() -> "DjangoHttpClient":
        return DjangoHttpClient(
            base_url=os.getenv("IOTSPLOIT_DJANGO_API_BASE_URL", "http://127.0.0.1:8888"),
            timeout_s=float(os.getenv("IOTSPLOIT_DJANGO_API_TIMEOUT_S", "5.0")),
            bearer_token=os.getenv("IOTSPLOIT_DJANGO_API_TOKEN") or None,
        )

    def headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        return headers

    def url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.config.base_url}{path}"

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, json=json)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = f"{method.upper()} {path}"
        try:
            resp = self._session.request(
                method=method.upper(),
                url=self.url(path),
                params=params,
                json=json,
                headers=self.headers(json_body=json is not None),
                timeout=self.config.timeout_s,
            )
        except requests.RequestException as exc:
            raise DjangoHttpError(
                f"Django API not reachable at {self.config.base_url}; start the IoTSploit Django backend first. {exc}"
            ) from exc

        if not 200 <= resp.status_code < 300:
            raise DjangoHttpError(
                f"{context} failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
                response_text=resp.text[:1000],
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise DjangoHttpError(f"{context} returned non-JSON response", response_text=resp.text[:1000]) from exc

        if not isinstance(payload, dict):
            raise DjangoHttpError(f"{context} returned unexpected JSON payload: {type(payload).__name__}")
        return payload
