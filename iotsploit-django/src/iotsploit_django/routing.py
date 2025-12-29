"""Channels routing for iotsploit-django.

Stage-5:
- Do not import consumers at import time to keep this module import-safe.
- Load websocket patterns from `iotsploit_django.websocket.routing` after Django setup.
"""

from __future__ import annotations

from django.apps import apps


def get_websocket_urlpatterns():
    if not apps.ready:
        return []
    from iotsploit_django.websocket.routing import websocket_urlpatterns

    return websocket_urlpatterns


# Channels expects `websocket_urlpatterns` by convention.
websocket_urlpatterns = get_websocket_urlpatterns()


