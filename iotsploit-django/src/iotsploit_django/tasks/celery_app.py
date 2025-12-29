"""Celery application (optional entrypoint).

The project currently relies on `@shared_task` tasks, so this module mainly
provides a conventional import path for workers if needed.
"""

from __future__ import annotations

import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")

app = Celery("iotsploit_django")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


