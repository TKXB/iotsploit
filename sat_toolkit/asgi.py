import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import sat_toolkit.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            sat_toolkit.routing.websocket_urlpatterns
        )
    ),
})
