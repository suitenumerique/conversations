"""Tests for the periodic Celery tasks that wrap management commands.

Celery runs eagerly in the test settings (`CELERY_TASK_ALWAYS_EAGER`), so
`.delay()` executes the task synchronously in-process.
"""

import io
import logging
from unittest.mock import patch

from django.core.management.base import CommandError

import pytest

from chat.tasks import deindex_inactive_collections_task, fetch_model_health_task
from conversations.celery_app import app


@patch("chat.tasks.call_command")
def test_fetch_model_health_task_calls_command_with_provider(call_command):
    """The task runs fetch_model_health with the given provider and a captured stdout."""
    fetch_model_health_task.delay("albert")

    call_command.assert_called_once()
    args, kwargs = call_command.call_args
    assert args == ("fetch_model_health", "--provider", "albert")
    assert isinstance(kwargs["stdout"], io.StringIO)


@patch("chat.tasks.call_command")
def test_fetch_model_health_task_logs_command_error(call_command, caplog):
    """A CommandError from the command is logged, not raised."""
    call_command.side_effect = CommandError("boom")

    with caplog.at_level(logging.ERROR, logger="chat.tasks"):
        fetch_model_health_task.delay("albert")

    assert "boom" in caplog.text
    assert "albert" in caplog.text


@patch("chat.tasks.call_command")
def test_fetch_model_health_task_reraises_other_errors(call_command):
    """A non-CommandError exception propagates so the task shows as failed."""
    call_command.side_effect = RuntimeError("unexpected")

    # CELERY_TASK_EAGER_PROPAGATES is not set, so .delay() would swallow the
    # exception into an EagerResult; call the task directly to see it raise.
    with pytest.raises(RuntimeError):
        fetch_model_health_task("albert")


@patch("chat.tasks.call_command")
def test_deindex_inactive_collections_task_calls_command(call_command):
    """The task runs deindex_inactive_collections with no arguments."""
    deindex_inactive_collections_task.delay()

    call_command.assert_called_once_with("deindex_inactive_collections")


@patch("chat.tasks.call_command")
def test_deindex_inactive_collections_task_logs_command_error(call_command, caplog):
    """A CommandError from the command is logged, not raised."""
    call_command.side_effect = CommandError("boom")

    with caplog.at_level(logging.ERROR, logger="chat.tasks"):
        deindex_inactive_collections_task.delay()

    assert "boom" in caplog.text


@patch("chat.tasks.call_command")
def test_deindex_inactive_collections_task_reraises_other_errors(call_command):
    """A non-CommandError exception propagates so the task shows as failed."""
    call_command.side_effect = RuntimeError("unexpected")

    # CELERY_TASK_EAGER_PROPAGATES is not set, so .delay() would swallow the
    # exception into an EagerResult; call the task directly to see it raise.
    with pytest.raises(RuntimeError):
        deindex_inactive_collections_task()


def test_tasks_are_registered_on_the_celery_app():
    """Both periodic tasks are registered under their dotted task name."""
    assert "chat.tasks.fetch_model_health_task" in app.tasks
    assert "chat.tasks.deindex_inactive_collections_task" in app.tasks
