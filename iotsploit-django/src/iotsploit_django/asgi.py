"""ASGI config for iotsploit-django.

Standalone default: use iotsploit-django settings by default.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Allow external override (Docker/supervisor/dev shells). Default to dev.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")

django_asgi_app = get_asgi_application()


async def assistant_lifespan(scope, receive, send):
    from iotsploit_django.agent_runtime.runtime import runtime

    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await runtime.close()
            await send({"type": "lifespan.shutdown.complete"})
            return

try:
    from iotsploit_django.routing import websocket_urlpatterns

    application = ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "lifespan": assistant_lifespan,
            "websocket": URLRouter(websocket_urlpatterns),
        }
    )
except Exception:
    # Fallback: HTTP only
    application = django_asgi_app

