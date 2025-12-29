"""ASGI config for iotsploit-django.

Stage-1 skeleton: use existing settings module by default.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sat_django_entry.settings")

django_asgi_app = get_asgi_application()

try:
    from iotsploit_django.routing import websocket_urlpatterns

    application = ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "websocket": URLRouter(websocket_urlpatterns),
        }
    )
except Exception:
    # Fallback: HTTP only
    application = django_asgi_app


