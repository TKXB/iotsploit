"""
sat_toolkit package.

Important: Keep imports lightweight so that "core-only" usage (or standalone-library extraction)
does not require Celery/Django to be installed.
"""

from __future__ import annotations

try:
    # Optional: only available in full Django/Celery runtime.
    from .celery import app as celery_app  # type: ignore

    __all__ = ("celery_app",)
except ModuleNotFoundError as e:
    # Celery is not installed/available in standalone contexts.
    # Only swallow the "celery" missing-module case; other import errors should surface.
    if e.name == "celery":
        __all__ = ()
    else:
        raise
