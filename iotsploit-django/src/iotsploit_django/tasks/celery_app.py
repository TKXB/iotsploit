"""Celery application (optional entrypoint).

The project currently relies on `@shared_task` tasks, so this module mainly
provides a conventional import path for workers if needed.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.signals import worker_init


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")

app = Celery("iotsploit_django")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Ensure `@shared_task` uses this configured app (instead of the implicit default
# which typically defaults to AMQP/RabbitMQ).
app.set_default()
app.set_current()


@worker_init.connect
def _load_shared_tasks_after_django_setup(**_kwargs):
    """Register `@shared_task` tasks after Django apps are ready.

    Celery may import this module before Django finishes setup; importing modules
    that define Django models too early can trigger AppRegistryNotReady.
    """
    try:
        from django.apps import apps
        if not apps.ready:
            import django
            django.setup()
    except Exception:
        # Best effort: if Django isn't available for some reason, let worker fail later.
        return

    # Import task definitions so Celery registers them for this worker.
    import iotsploit_django.tasks.legacy_tasks_impl  # noqa: F401


