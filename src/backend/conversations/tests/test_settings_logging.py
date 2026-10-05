"""Tests for the logging settings."""

from unittest import mock

import pytest

from conversations.observability_settings import ObservabilitySettings
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
