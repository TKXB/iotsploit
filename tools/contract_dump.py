"""
Contract dump utilities for freezing HTTP/WS interfaces (Stage 0).

Outputs are meant to be committed so refactors can prove they didn't break
public endpoints.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable


def _django_setup() -> None:
    # Stage-2+: use iotsploit-django settings so ROOT_URLCONF points to
    # `iotsploit_django.urls` (route aggregation layer).
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    import django  # type: ignore

    django.setup()


@dataclass(frozen=True)
class HttpRoute:
    name: str
    pattern: str


@dataclass(frozen=True)
class WsRoute:
    pattern: str
    consumer: str


def dump_http_routes() -> list[dict[str, Any]]:
    _django_setup()
    from django.urls.resolvers import URLPattern, URLResolver
    from iotsploit_django.web.api import urls as api_urls  # type: ignore

    def _walk(patterns: list[Any], prefix: str = "") -> list[HttpRoute]:
        out: list[HttpRoute] = []
        for p in patterns:
            if isinstance(p, URLPattern):
                name = getattr(p, "name", None)
                if not name:
                    continue
                out.append(HttpRoute(name=str(name), pattern=f"{prefix}{p.pattern}"))
            elif isinstance(p, URLResolver):
                out.extend(_walk(list(p.url_patterns), prefix=f"{prefix}{p.pattern}"))
        return out

    # Note: `sat_django_entry.urls` historically mounts API under `/api/`.
    # The contract snapshots store patterns *without* the `api/` prefix, so we
    # keep dumping the subtree under `iotsploit_django.web.api.urls` directly.
    routes = _walk(list(api_urls.urlpatterns), prefix="")

    routes_sorted = sorted(routes, key=lambda r: (r.pattern, r.name))
    return [{"name": r.name, "pattern": r.pattern} for r in routes_sorted]


def dump_ws_routes() -> list[dict[str, Any]]:
    _django_setup()
    from iotsploit_django import routing  # type: ignore

    out: list[WsRoute] = []
    for p in getattr(routing, "websocket_urlpatterns", []):
        # URLPattern has `.pattern` and `.callback` (consumer as ASGI callable)
        patt = str(getattr(p, "pattern", ""))
        cb = getattr(p, "callback", None)
        consumer = ""
        if cb is not None:
            consumer = getattr(cb, "__qualname__", "") or getattr(cb, "__name__", "") or repr(cb)
            consumer = consumer.replace(".as_asgi.<locals>.app", "").strip()
        out.append(WsRoute(pattern=patt, consumer=consumer))

    out_sorted = sorted(out, key=lambda r: (r.pattern, r.consumer))
    return [{"pattern": r.pattern, "consumer": r.consumer} for r in out_sorted]


def write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def main(argv: Iterable[str] | None = None) -> int:
    http = dump_http_routes()
    ws = dump_ws_routes()

    write_json("docs/contracts/http_routes.json", http)
    write_json("docs/contracts/ws_routes.json", ws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


