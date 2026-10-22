from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from iotsploit_core.domain.plugin import PluginMeta
from iotsploit_core.ports.plugin_repo import PluginMetaRepository


@dataclass(frozen=True)
class DjangoHttpApiConfig:
    base_url: str
    timeout_s: float = 5.0


class HttpPluginMetaRepository(PluginMetaRepository):
    """Read plugin metadata from the Django source of truth."""

    def __init__(self, *, base_url: str, timeout_s: float = 5.0) -> None:
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required for HttpPluginMetaRepository")
        self._cfg = DjangoHttpApiConfig(base_url=base_url, timeout_s=float(timeout_s))
        self._session = requests.Session()

    @staticmethod
    def from_env() -> "HttpPluginMetaRepository":
        base_url = os.getenv("IOTSPLOIT_DJANGO_API_BASE_URL", "http://127.0.0.1:8888")
        timeout_s = float(os.getenv("IOTSPLOIT_DJANGO_API_TIMEOUT_S", "5.0"))
        return HttpPluginMetaRepository(base_url=base_url, timeout_s=timeout_s)

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

    def upsert(self, meta: PluginMeta) -> None:
        # Remote discovery must never write caller-controlled module paths into
        # Django. Trusted local composition roots use DjangoPluginMetaRepository.
        return None

    def list_enabled(self) -> list[PluginMeta]:
        resp = self._session.get(
            self._url("/api/plugins/exploits/enabled/"),
            headers=self._headers(),
            timeout=self._cfg.timeout_s,
        )
        self._raise_for_bad_response(resp, context="GET /api/plugins/exploits/enabled/")
        payload: dict[str, Any] = resp.json()
        if payload.get("status") not in (None, "success"):
            raise RuntimeError(f"GET /api/plugins/exploits/enabled/ returned error: {payload!r}")

        items = payload.get("plugins") or []
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected plugins payload: {items!r}")

        metas: list[PluginMeta] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            metas.append(
                PluginMeta(
                    name=str(it.get("name") or ""),
                    module_path=str(it.get("module_path") or ""),
                    enabled=bool(it.get("enabled", True)),
                    description=str(it.get("description") or ""),
                    author=str(it.get("author") or ""),
                    license=str(it.get("license") or ""),
                    parameters=it.get("parameters") if isinstance(it.get("parameters"), dict) else None,
                    requirements=tuple(it.get("requirements") or ()),
                )
            )
        return [m for m in metas if m.name and m.module_path]

    def disable_missing(self, names: set[str]) -> int:
        # SSOT note: do NOT disable globally based on a single MCP node's filesystem.
        # In multi-node deployments, a plugin may exist on another node.
        return 0
