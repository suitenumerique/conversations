"""Provider errors reach the logs by type and status only, never by message."""

import logging

import structlog
from pydantic_ai.exceptions import ModelHTTPError, ModelRetry

# A provider error body echoing the input, which must never reach the logs.
PROVIDER_BODY = "echoed secret document passage"

# The logger django-structlog writes its Celery task lines with.
celery_receiver_logger = structlog.get_logger("django_structlog.celery.receivers")
# Any of our own loggers.
app_logger = structlog.get_logger("chat.tools.example")


def _provider_error():
    return ModelHTTPError(status_code=503, model_name="m", body=PROVIDER_BODY)


def test_a_failed_task_names_a_provider_error_without_its_body(json_logs):
    """`task_failed` as django-structlog logs it: message, exception and traceback."""
    exc = _provider_error()
    try:
        raise exc
    except ModelHTTPError:
        celery_receiver_logger.exception("task_failed", error=str(exc), exception=exc)

    lines = json_logs()
    [line] = [line for line in lines if line["event"] == "task_failed"]
    assert line["error_type"] == "ModelHTTPError"
    assert line["status_code"] == 503
    assert "error" not in line
    assert "exception" not in line
    assert PROVIDER_BODY not in str(lines)


def test_a_retrying_task_names_a_provider_error_without_its_body(json_logs):
    """`task_retrying` as django-structlog logs it: the exception as `reason`."""
    celery_receiver_logger.log(logging.INFO, "task_retrying", reason=_provider_error())

    lines = json_logs()
    [line] = [line for line in lines if line["event"] == "task_retrying"]
    assert line["error_type"] == "ModelHTTPError"
    assert line["status_code"] == 503
    assert "reason" not in line
    assert PROVIDER_BODY not in str(lines)


def test_a_failed_task_keeps_the_traceback_of_other_errors(json_logs):
    """Only provider errors are scrubbed: a server bug keeps what debugging needs."""
    exc = RuntimeError("server-side bug")
    try:
        raise exc
    except RuntimeError:
        celery_receiver_logger.exception("task_failed", error=str(exc), exception=exc)

    [line] = [line for line in json_logs() if line["event"] == "task_failed"]
    assert line["error"] == "server-side bug"
    assert "Traceback" in line["exception"]


def _assert_scrubbed(lines, event):
    """The line names the provider error by type and status, and nothing renders its body."""
    [line] = [line for line in lines if line["event"] == event]
    assert line["error_type"] == "ModelHTTPError"
    assert line["status_code"] == 503
    assert "exception" not in line
    assert PROVIDER_BODY not in str(lines)


def test_an_exception_raised_from_a_provider_error_is_scrubbed(json_logs):
    """`raise ModelRetry(...) from exc`: the traceback would render the cause."""
    try:
        try:
            raise _provider_error()
        except ModelHTTPError as exc:
            raise ModelRetry("could not summarize") from exc
    except ModelRetry:
        app_logger.exception("summarize_unexpected_error")

    _assert_scrubbed(json_logs(), "summarize_unexpected_error")


def test_an_exception_raised_while_handling_a_provider_error_is_scrubbed(json_logs):
    """Implicit chaining: the traceback renders "During handling of the above..."."""
    try:
        try:
            raise _provider_error()
        except ModelHTTPError:
            # The implicit chain is the case under test.
            raise RuntimeError("cleanup failed")  # pylint: disable=raise-missing-from  # noqa: B904
    except RuntimeError:
        app_logger.warning("web_page_summarize_failed", exc_info=True)

    _assert_scrubbed(json_logs(), "web_page_summarize_failed")


def test_a_stdlib_logged_provider_error_is_scrubbed(json_logs):
    """Libraries log through stdlib `logging`, not structlog: same scrubbing."""
    try:
        raise _provider_error()
    except ModelHTTPError:
        logging.getLogger("some.library").exception("request to the provider failed")

    _assert_scrubbed(json_logs(), "request to the provider failed")
