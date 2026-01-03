"""ASGI config for iotsploit-django.

Standalone default: use iotsploit-django settings by default.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Allow external override (Docker/supervisor/dev shells). Default to dev.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")

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


