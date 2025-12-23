"""
sat_toolkit.models

Important boundary rule (Ports & Adapters):
- This package must NOT eagerly import Django ORM models at import time.
- Django-specific models live in adapter modules (e.g. `sat_toolkit.adapters.django.*`).

This package is intentionally kept lightweight and framework-agnostic.
Do NOT re-export Django ORM models here.
"""

__all__ = []

