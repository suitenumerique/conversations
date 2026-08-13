"""Global fixtures for the backend tests."""

import freezegun
import posthog
import pytest
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.sync import SyncBackend
from rest_framework.test import APIClient
from urllib3.connectionpool import HTTPConnectionPool

# freeze_time() scans every loaded module's attributes via getattr(), which
# triggers langfuse.api's lazy __getattr__-based submodule imports. If that
# first-time import of a langfuse pydantic model happens while datetime is
# already patched, schema generation for its datetime field breaks
# permanently for the rest of the worker process. Skip scanning langfuse.
freezegun.configure(extend_ignore_list=["langfuse"])


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

    Both transports are covered: urllib3, used by `requests` (still pulled in by
    third-party libraries such as mozilla-django-oidc, posthog and the OTLP
    exporter), and httpcore, used by `httpx` for our own outbound calls.

    The httpcore patch sits on the network backend rather than on the connection
    pool, which is where respx installs its own patch. A mocked route is served
    by respx and never opens a socket, so this guard only fires for calls no test
    mocked at all.

    Credits: https://blog.jerrycodes.com/no-http-requests/
    """

    allowed_hosts = {"localhost", "127.0.0.1", "minio", "minio:9000"}
    original_urlopen = HTTPConnectionPool.urlopen

    def urlopen_mock(self, method, url, *args, **kwargs):
        if self.host in allowed_hosts:
            return original_urlopen(self, method, url, *args, **kwargs)

        raise RuntimeError(f"The test was about to {method} {self.scheme}://{self.host}{url}")

    monkeypatch.setattr("urllib3.connectionpool.HTTPConnectionPool.urlopen", urlopen_mock)

    original_connect_tcp = SyncBackend.connect_tcp
    original_connect_tcp_async = AnyIOBackend.connect_tcp

    def _refuse(host, port):
        """Raise unless the connection targets an allowed host."""
        if host not in allowed_hosts and f"{host}:{port}" not in allowed_hosts:
            raise RuntimeError(f"The test was about to connect to {host}:{port}")

    def connect_tcp_mock(self, host, port, *args, **kwargs):
        _refuse(host, port)
        return original_connect_tcp(self, host, port, *args, **kwargs)

    async def connect_tcp_async_mock(self, host, port, *args, **kwargs):
        _refuse(host, port)
        return await original_connect_tcp_async(self, host, port, *args, **kwargs)

    monkeypatch.setattr("httpcore._backends.sync.SyncBackend.connect_tcp", connect_tcp_mock)
    monkeypatch.setattr("httpcore._backends.anyio.AnyIOBackend.connect_tcp", connect_tcp_async_mock)


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
