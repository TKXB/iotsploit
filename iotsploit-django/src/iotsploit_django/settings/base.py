"""Base settings for iotsploit-django.

Stage-1 strategy:
- Keep behavior consistent by importing from current `sat_django_entry.settings`.
- Later stages will progressively move settings into this package.
"""

from sat_django_entry.settings import *  # noqa: F401,F403

# Stage-2: switch the host URLConf to iotsploit-django aggregation layer.
# Public paths must remain stable; only the composition of URL patterns moves.
ROOT_URLCONF = "iotsploit_django.urls"


