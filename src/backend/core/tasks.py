"""Celery tasks for the core app."""

import structlog

from conversations.celery_app import app

logger = structlog.get_logger(__name__)


@app.task
def debug_add(x, y):
    """Trivial task used to check that Celery is wired up correctly."""
    result = x + y
    logger.info("debug_add", x=x, y=y, result=result)
    return result
