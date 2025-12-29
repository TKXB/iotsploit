"""
Django -> SQLAlchemy wiring.

Reads Django settings and builds SQLAlchemy engine/session/Base via the pure SQLAlchemy adapter.
"""

from __future__ import annotations

from django.conf import settings

from iotsploit_django.adapters.sqlalchemy.database import create_sqlalchemy_db


def get_default_sqlalchemy_db():
    # Use Django's configured DB file (current project uses SQLite)
    db_path = settings.DATABASES["default"]["NAME"]
    db_url = f"sqlite:///{db_path}"
    return create_sqlalchemy_db(db_url, echo=False)


