from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Change this line to point to the correct settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')

# Create celery app
app = Celery('sat_toolkit')

# Load task modules from all registered Django app configs.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load tasks from all registered apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 