"""
ASGI config for sat_django_entry project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Set up Django settings first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')

# Initialize Django ASGI application early to ensure the AppRegistry is populated
django_asgi_app = get_asgi_application()

# Import routing after Django is set up
import sat_toolkit.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            sat_toolkit.routing.websocket_urlpatterns
        )
    ),
})
