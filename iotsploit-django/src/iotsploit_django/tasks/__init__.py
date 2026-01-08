"""Celery tasks for iotsploit-django (outer ring).

Important:
- Tasks are implemented using `@shared_task` in `legacy_tasks_impl.py`.
- To avoid Celery falling back to the implicit default app (AMQP/RabbitMQ),
  import our configured app early so it becomes the default/current app.
"""

from iotsploit_django.tasks.celery_app import app as celery_app  # noqa: F401

__all__ = ["celery_app"]


