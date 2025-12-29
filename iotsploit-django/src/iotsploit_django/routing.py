"""Channels routing for iotsploit-django.

Stage-1 skeleton:
- Do not import `sat_toolkit.routing` at import time to keep this module import-safe.
- Expose a helper that loads the legacy patterns after Django setup.
"""

from __future__ import annotations

from django.apps import apps


def get_websocket_urlpatterns():
    if not apps.ready:
        return []
    from sat_toolkit.routing import websocket_urlpatterns

    return websocket_urlpatterns


# Channels expects `websocket_urlpatterns` by convention.
websocket_urlpatterns = get_websocket_urlpatterns()


