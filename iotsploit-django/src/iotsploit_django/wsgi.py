"""WSGI config for iotsploit-django.

Standalone default: use iotsploit-django settings by default.
"""

import os

from django.core.wsgi import get_wsgi_application

# Allow external override (Docker/supervisor/dev shells). Default to dev.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")

application = get_wsgi_application()


