from __future__ import annotations

# Stage-4: reuse existing Django ORM repositories (legacy location) behind a
# stable iotsploit-django import path.
from iotsploit_django.adapters.django.plugins.repos import (  # noqa: F401
    DjangoPluginGroupRepository,
    DjangoPluginMetaRepository,
)

__all__ = ["DjangoPluginMetaRepository", "DjangoPluginGroupRepository"]


