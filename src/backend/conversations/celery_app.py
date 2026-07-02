"""Conversations celery configuration file."""

import os

from celery import Celery
from configurations.importer import install

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conversations.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Development")

# Bootstrap django-configurations so the class-based settings are loaded.
# manage.py/wsgi/asgi do this for us, but the celery entrypoint must do it itself,
# before anything reads django.conf.settings.
install(check_options=True)

# Can be loaded only after install call.
from django.conf import settings  # pylint: disable=wrong-import-position

app = Celery("conversations")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
