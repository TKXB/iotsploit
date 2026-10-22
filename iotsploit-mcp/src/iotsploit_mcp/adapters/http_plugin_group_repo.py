from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from iotsploit_core.domain.execution_plan import GroupStepSpec, PluginGroupSpec, PluginStepSpec
from iotsploit_core.ports.plugin_repo import PluginGroupRepository


@dataclass(frozen=True)
class DjangoHttpApiConfig:
    base_url: str
    timeout_s: float = 5.0


class HttpPluginGroupRepository(PluginGroupRepository):
    """PluginGroupRepository over iotsploit_django HTTP API (SSOT).

    Endpoints:
    - GET /api/plugin_groups/enabled/
    - GET /api/plugin_groups/<name>/
    """

    def __init__(self, *, base_url: str, timeout_s: float = 5.0) -> None:
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required for HttpPluginGroupRepository")
        self._cfg = DjangoHttpApiConfig(base_url=base_url, timeout_s=float(timeout_s))
        self._session = requests.Session()

    @staticmethod
    def from_env() -> "HttpPluginGroupRepository":
        base_url = os.getenv("IOTSPLOIT_DJANGO_API_BASE_URL", "http://127.0.0.1:8888")
        timeout_s = float(os.getenv("IOTSPLOIT_DJANGO_API_TIMEOUT_S", "5.0"))
        return HttpPluginGroupRepository(base_url=base_url, timeout_s=timeout_s)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        return headers

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self._cfg.base_url}{path}"

    @staticmethod
    def _raise_for_bad_response(resp: requests.Response, *, context: str) -> None:
        if 200 <= resp.status_code < 300:
            return
        raise RuntimeError(f"{context} failed: HTTP {resp.status_code}: {resp.text[:500]}")

    @staticmethod
    def _to_spec(payload: dict[str, Any]) -> PluginGroupSpec:
        plugin_steps: list[PluginStepSpec] = []
        for s in payload.get("plugin_steps") or []:
            if not isinstance(s, dict):
                continue
            plugin_steps.append(
                PluginStepSpec(
                    sequence=int(s.get("sequence", 100)),
                    plugin_name=str(s.get("plugin_name") or ""),
                    ignore_fail=bool(s.get("ignore_fail", False)),
                )
            )

        group_steps: list[GroupStepSpec] = []
        for s in payload.get("group_steps") or []:
            if not isinstance(s, dict):
                continue
            group_steps.append(
                GroupStepSpec(
                    sequence=int(s.get("sequence", 100)),
                    group_name=str(s.get("group_name") or ""),
                    ignore_fail=bool(s.get("ignore_fail", False)),
                    force_exec=bool(s.get("force_exec", False)),
                )
            )

        return PluginGroupSpec(
            name=str(payload.get("name") or ""),
            enabled=bool(payload.get("enabled", True)),
            plugin_steps=plugin_steps,
            group_steps=group_steps,
        )

    def list_enabled_groups(self) -> list[PluginGroupSpec]:
        resp = self._session.get(
            self._url("/api/plugin_groups/enabled/"),
            headers=self._headers(),
            timeout=self._cfg.timeout_s,
        )
        self._raise_for_bad_response(resp, context="GET /api/plugin_groups/enabled/")
        payload: dict[str, Any] = resp.json()
        if payload.get("status") not in (None, "success"):
            raise RuntimeError(f"GET /api/plugin_groups/enabled/ returned error: {payload!r}")

        items = payload.get("groups") or []
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected groups payload: {items!r}")
        out: list[PluginGroupSpec] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            spec = self._to_spec(it)
            if spec.name:
                out.append(spec)
        return out

    def get_group(self, name: str) -> PluginGroupSpec | None:
        if not name:
            return None
        resp = self._session.get(
            self._url(f"/api/plugin_groups/{name}/"),
            headers=self._headers(),
            timeout=self._cfg.timeout_s,
        )
        if resp.status_code == 404:
            return None
        self._raise_for_bad_response(resp, context=f"GET /api/plugin_groups/{name}/")
        payload: dict[str, Any] = resp.json()
        if payload.get("status") not in (None, "success"):
            raise RuntimeError(f"GET /api/plugin_groups/{name}/ returned error: {payload!r}")
        g = payload.get("group")
        if not isinstance(g, dict):
            return None
        spec = self._to_spec(g)
        return spec if spec.name else None


