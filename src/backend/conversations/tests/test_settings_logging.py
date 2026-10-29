"""Tests for the logging settings."""

from unittest import mock

import pytest

from conversations.observability_settings import ObservabilitySettings, scrub_transaction_queries
from conversations.settings import Base


@pytest.mark.parametrize("logger_name", ["httpx", "httpx2"])
def test_production_logging_silences_request_urls(logger_name):
    """Request urls carry user queries: their INFO logs must stay off in production."""
    assert ObservabilitySettings.LOGGING["loggers"][logger_name]["level"] == "WARNING"


def test_sentry_does_not_capture_request_bodies_nor_local_variables():
    """Request bodies and stack frame locals carry user prompts: keep them out of Sentry."""

    class TestSettings(Base):
        """Fake test settings."""

        SENTRY_DSN = "https://key@sentry.example.com/1"

    with mock.patch("conversations.settings.sentry_sdk.init") as sentry_init:
        TestSettings().post_setup()

    assert sentry_init.call_args.kwargs["max_request_body_size"] == "never"
    assert sentry_init.call_args.kwargs["include_local_variables"] is False


def _sentry_init_kwargs(**settings):
    """Run post_setup with the given settings and return the sentry_sdk.init kwargs."""
    test_settings = type("TestSettings", (Base,), settings)
    with mock.patch("conversations.settings.sentry_sdk.init") as sentry_init:
        test_settings().post_setup()
    return sentry_init.call_args.kwargs


def test_sentry_traces_disabled_by_default():
    """None, not 0: at 0 the SDK still follows a sampled sentry-trace header from the frontend."""
    kwargs = _sentry_init_kwargs(SENTRY_DSN="https://key@sentry.example.com/1")

    assert kwargs["traces_sample_rate"] is None


def test_sentry_traces_sample_rate_from_setting():
    """The configured rate is passed to Sentry, with the query scrubbing hook."""
    kwargs = _sentry_init_kwargs(
        SENTRY_DSN="https://key@sentry.example.com/1", SENTRY_TRACES_SAMPLE_RATE=0.25
    )

    assert kwargs["traces_sample_rate"] == 0.25
    assert kwargs["before_send_transaction"] is scrub_transaction_queries


def test_scrub_transaction_queries_strips_query_strings():
    """Query strings carry user input (web search ?q=, ?title=): they must never reach Sentry."""
    event = {
        "request": {"url": "http://localhost/api/v1.0/chats/", "query_string": "title=secret"},
        "spans": [
            {"data": {"url": "https://search.example.com/search", "http.query": "q=secret"}},
            {"data": {"url.query": "q=secret"}},
            {"op": "db"},
        ],
    }

    assert "secret" not in str(scrub_transaction_queries(event, {}))
