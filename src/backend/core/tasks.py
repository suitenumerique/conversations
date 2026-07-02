"""Celery tasks for the core app."""

import logging

from conversations.celery_app import app

logger = logging.getLogger(__name__)


@app.task
def debug_add(x, y):
    """Trivial task used to check that Celery is wired up correctly."""
    result = x + y
    logger.info("debug_add(%s, %s) = %s", x, y, result)
    return result
