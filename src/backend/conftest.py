"""Global fixtures for the backend tests."""

import posthog
import pytest
from rest_framework.test import APIClient
from urllib3.connectionpool import HTTPConnectionPool


@pytest.fixture
def api_client():
    """Fixture to provide an API client for testing."""
    return APIClient()


@pytest.fixture(autouse=True)
def no_http_requests(monkeypatch):
    """
    Prevents HTTP requests from being made during tests.
    This is useful for tests that do not require actual HTTP requests
    and helps to avoid network-related issues.

    Credits: https://blog.jerrycodes.com/no-http-requests/
    """

    allowed_hosts = {"localhost", "minio", "minio:9000"}
    original_urlopen = HTTPConnectionPool.urlopen

    def urlopen_mock(self, method, url, *args, **kwargs):
        if self.host in allowed_hosts:
            return original_urlopen(self, method, url, *args, **kwargs)

        raise RuntimeError(f"The test was about to {method} {self.scheme}://{self.host}{url}")

    monkeypatch.setattr("urllib3.connectionpool.HTTPConnectionPool.urlopen", urlopen_mock)


@pytest.fixture(name="feature_flags", scope="function")
def feature_flags_fixture(settings):
    """
    Ease feature flags setting in tests by working on a copy
    to allow proper restore by SettingsWrapper after the test.
    """
    settings.FEATURE_FLAGS = settings.FEATURE_FLAGS.model_copy(deep=True)
    yield settings.FEATURE_FLAGS


@pytest.fixture(name="posthog", scope="function")
def posthog_fixture(settings):
    """Mock PostHog in tests to avoid real network calls."""
    settings.POSTHOG_KEY = {"id": "132456", "host": "https://eu.i.posthog-test.com"}

    posthog.api_key = settings.POSTHOG_KEY["id"]
    posthog.host = settings.POSTHOG_KEY["host"]

    yield posthog

    posthog.api_key = None
    posthog.host = None
