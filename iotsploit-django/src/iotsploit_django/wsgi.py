"""WSGI config for iotsploit-django.

Stage-1 skeleton: keep existing settings module by default.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sat_django_entry.settings")

application = get_wsgi_application()


