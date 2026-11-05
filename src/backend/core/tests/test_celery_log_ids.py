"""A task queued during a request logs under that request's ids.

Tests run Celery eagerly, which never publishes, so django-structlog's publish
receiver never runs there. This publishes for real, into kombu's in-memory
broker (`send_task` skips the eager shortcut), then runs the message the way a
worker does.
"""

import itertools

import pytest
import structlog
from celery import signals as celery_signals
from celery.worker.request import Request
from django_structlog.celery.steps import DjangoStructLogInitStep

from conversations.celery_app import app

logger = structlog.get_logger("core.tests.celery")


@app.task(name="core.tests.log_ids")
def log_ids_task():
    """Write one line from inside the task."""
    logger.info("test_task_ran")


@pytest.fixture(name="boot_worker")
def boot_worker_fixture():
    """Boot django-structlog's worker step on demand, as our worker does; undo it.

    Left connected, its task_prerun receiver would clear the context of every
    eager task in the other tests.
    """
    receivers = []

    def boot():
        assert DjangoStructLogInitStep in app.steps["worker"]
        receivers.append(DjangoStructLogInitStep(parent=None).receiver)

    yield boot
    for receiver, name in itertools.product(
        receivers,
        (
            "before_task_publish",
            "after_task_publish",
            "task_prerun",
            "task_retry",
            "task_success",
            "task_failure",
            "task_revoked",
            "task_unknown",
            "task_rejected",
        ),
    ):
        getattr(celery_signals, name).disconnect(getattr(receiver, f"receiver_{name}"))


@pytest.fixture(name="no_result_backend")
def no_result_backend_fixture(monkeypatch):
    """Fail on any use of the result backend.

    There is no Redis behind it in CI: a test that needs it passes locally, where
    the dev Redis runs, and fails there.
    """

    def unavailable(*args, **kwargs):
        raise AssertionError("the result backend must not be used")

    # The two calls that reach Redis: subscribing on send, storing on completion
    # (`mark_as_done` and `mark_as_failure` only store through `store_result`).
    for name in ("on_task_call", "store_result"):
        monkeypatch.setattr(app.backend, name, unavailable)


@pytest.fixture(name="memory_broker")
def memory_broker_fixture():
    """An in-memory broker to publish to; leave no context behind."""
    with app.connection_for_write("memory://") as connection:
        yield connection
    # The worker side binds task_id in this thread's context.
    structlog.contextvars.clear_contextvars()


@pytest.mark.usefixtures("no_result_backend")
def test_a_queued_task_logs_under_the_request_ids(memory_broker, boot_worker, json_logs):
    """request_id and user_id travel in the message and are bound in the worker."""
    # Published from the web process: only its own receivers are connected.
    with memory_broker.SimpleQueue(app.conf.task_default_queue) as queue:
        with structlog.contextvars.bound_contextvars(request_id="rid-1", user_id="u-1"):
            # No result: sending would otherwise subscribe to it in the result
            # backend, and the worker path would store it there.
            app.send_task(log_ids_task.name, connection=memory_broker, ignore_result=True)
        message = queue.get(timeout=1)

    context = message.headers["__django_structlog__"]
    assert (context["request_id"], context["user_id"]) == ("rid-1", "u-1")

    # What the worker does with a message it received.
    boot_worker()
    Request(message, app=app, task=log_ids_task).execute()

    [line] = [line for line in json_logs() if line["event"] == "test_task_ran"]
    assert line["request_id"] == "rid-1"
    assert line["user_id"] == "u-1"
    assert line["task_id"] == message.headers["id"]
