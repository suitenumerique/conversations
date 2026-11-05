"""What Sentry receives from our structlog lines and from provider errors."""

import json

import pytest
import sentry_sdk
import structlog
from pydantic_ai.exceptions import ModelHTTPError, ModelRetry
from sentry_sdk.transport import Transport

from conversations.observability_settings import scrub_sentry_breadcrumb, scrub_sentry_event

# A provider error body echoing the input, which must never reach Sentry.
PROVIDER_BODY = "echoed secret document passage"

logger = structlog.get_logger("chat.tools.example")


class CaptureTransport(Transport):
    """Keep the events Sentry would send, instead of sending them."""

    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        self.events.extend(item.payload.json for item in envelope.items if item.type == "event")


@pytest.fixture(name="sentry_events")
def sentry_events_fixture():
    """A Sentry client configured like production's hooks; yield what it captures."""
    transport = CaptureTransport()
    sentry_sdk.init(
        dsn="https://key@sentry.invalid/1",
        transport=transport,
        before_send=scrub_sentry_event,
        before_breadcrumb=scrub_sentry_breadcrumb,
    )
    yield transport.events
    sentry_sdk.init()  # no DSN: back to an inactive client


def _provider_error():
    return ModelHTTPError(status_code=503, model_name="m", body=PROVIDER_BODY)


def test_a_logged_exception_reaches_sentry_with_its_stack_trace(sentry_events):
    """Titled by the event name, fields as extra, request id as a tag."""
    with structlog.contextvars.bound_contextvars(request_id="rid-1"):
        try:
            raise RuntimeError("server-side bug")
        except RuntimeError:
            logger.exception("presentation_build_failed", attachment_id="a-1")

    [event] = sentry_events
    assert event["logentry"]["message"] == "presentation_build_failed"
    assert event["extra"]["attachment_id"] == "a-1"
    assert event["tags"]["request_id"] == "rid-1"
    [exception] = event["exception"]["values"]
    assert exception["type"] == "RuntimeError"
    assert exception["stacktrace"]["frames"]


def test_a_logged_provider_error_reaches_sentry_without_its_body(sentry_events):
    """The log line keeps only type and status, so does its Sentry event."""
    try:
        try:
            raise _provider_error()
        except ModelHTTPError as exc:
            raise ModelRetry("could not summarize") from exc
    except ModelRetry:
        logger.exception("summarize_unexpected_error")

    [event] = sentry_events
    assert event["logentry"]["message"] == "summarize_unexpected_error"
    assert event["extra"]["error_type"] == "ModelHTTPError"
    assert event["extra"]["status_code"] == 503
    assert PROVIDER_BODY not in json.dumps(event, default=str)


def test_a_captured_provider_error_reaches_sentry_without_its_body(sentry_events):
    """What the Django and Celery integrations send: the exception chain itself."""
    try:
        try:
            raise _provider_error()
        except ModelHTTPError as exc:
            raise ModelRetry("could not summarize") from exc
    except ModelRetry as exc:
        sentry_sdk.capture_exception(exc)

    [event] = sentry_events
    values = {value["type"]: value["value"] for value in event["exception"]["values"]}
    assert values == {"ModelHTTPError": "status_code: 503", "ModelRetry": "could not summarize"}
    assert PROVIDER_BODY not in json.dumps(event, default=str)


def test_a_structlog_breadcrumb_is_named_by_its_event(sentry_events):
    """Breadcrumbs read as event names with their fields, not dict reprs."""
    logger.info("summarize_chunk_started", chunk=1)
    logger.error("summarize_merge_failed")

    [event] = sentry_events
    [crumb] = [
        crumb
        for crumb in event["breadcrumbs"]["values"]
        if crumb["message"] == "summarize_chunk_started"
    ]
    assert crumb["data"]["chunk"] == 1
