"""Tests for the Docs integration configuration validation in post_setup."""

import pytest

from conversations.settings import Base


def test_docs_base_url_without_oidc_store_access_token_raises():
    """DOCS_BASE_URL set without OIDC_STORE_ACCESS_TOKEN enabled must raise ValueError."""

    class TestSettings(Base):
        """Fake test settings with Docs enabled but OIDC token storage off."""

        DOCS_BASE_URL = "http://docs.example.com/"
        OIDC_STORE_ACCESS_TOKEN = False

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "DOCS_BASE_URL" in str(excinfo.value)
    assert "OIDC_STORE_ACCESS_TOKEN" in str(excinfo.value)


def test_docs_base_url_with_oidc_store_access_token_does_not_raise():
    """DOCS_BASE_URL set (HTTPS) with OIDC_STORE_ACCESS_TOKEN enabled must not raise."""

    class TestSettings(Base):
        """Fake test settings with Docs enabled and OIDC token storage on."""

        DOCS_BASE_URL = "https://docs.example.com/"
        OIDC_STORE_ACCESS_TOKEN = True

    # Should not raise
    TestSettings().post_setup()


def test_docs_base_url_http_non_localhost_raises():
    """A non-HTTPS DOCS_BASE_URL on a remote host must raise ValueError."""

    class TestSettings(Base):
        """Fake test settings with a plaintext remote Docs URL."""

        DOCS_BASE_URL = "http://docs.example.com/"
        OIDC_STORE_ACCESS_TOKEN = True

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "HTTPS" in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/",
        "http://127.0.0.1:8000/",
    ],
)
def test_docs_base_url_http_localhost_does_not_raise(url):
    """Plaintext localhost DOCS_BASE_URL is exempted for local development."""

    class TestSettings(Base):
        """Fake test settings with a plaintext localhost Docs URL."""

        DOCS_BASE_URL = url
        OIDC_STORE_ACCESS_TOKEN = True

    # Should not raise — localhost is the dev escape hatch.
    TestSettings().post_setup()


def test_docs_base_url_none_does_not_raise():
    """DOCS_BASE_URL=None (default) must never raise regardless of OIDC settings."""

    class TestSettings(Base):
        """Fake test settings with Docs disabled."""

        DOCS_BASE_URL = None
        OIDC_STORE_ACCESS_TOKEN = False

    # Should not raise
    TestSettings().post_setup()


def test_docs_base_url_empty_string_does_not_raise():
    """An empty DOCS_BASE_URL is falsy and must not trigger the validation error."""

    class TestSettings(Base):
        """Fake test settings with empty Docs URL."""

        DOCS_BASE_URL = ""
        OIDC_STORE_ACCESS_TOKEN = False

    # Should not raise — empty string is falsy, same as None
    TestSettings().post_setup()
