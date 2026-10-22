"""Production settings for iotsploit-django (standalone)."""

import os

from django.core.exceptions import ImproperlyConfigured

from iotsploit_django.settings.base import *  # noqa: F401,F403


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production")
    return value


def _required_list(name: str) -> list[str]:
    values = [value.strip() for value in _required_environment(name).split(",") if value.strip()]
    if not values:
        raise ImproperlyConfigured(f"{name} must contain at least one value")
    return values


DEBUG = False
SECRET_KEY = _required_environment("SECRET_KEY")
ALLOWED_HOSTS = _required_list("ALLOWED_HOSTS")

CORS_ALLOW_ALL_ORIGINS = False
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOWED_ORIGINS = _required_list("CORS_ALLOWED_ORIGINS")

