"""Tests for the Staan endpoint validation in post_setup."""

import pytest

from conversations.settings import Base


def test_plaintext_staan_url_raises():
    """A plaintext remote STAAN_API_URL would send STAAN_API_KEY in the clear."""

    class TestSettings(Base):
        """Fake test settings with a plaintext remote Staan URL."""

        STAAN_API_URL = "http://api.staan.ai"

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "STAAN_API_URL" in str(excinfo.value)
    assert "HTTPS" in str(excinfo.value)


def test_https_staan_url_does_not_raise():
    """The expected configuration must not raise."""

    class TestSettings(Base):
        """Fake test settings with an encrypted Staan URL."""

        STAAN_API_URL = "https://api.staan.ai"

    # Should not raise
    TestSettings().post_setup()


def test_uppercase_scheme_does_not_raise():
    """The scheme comparison must be case-insensitive."""

    class TestSettings(Base):
        """Fake test settings with an uppercased scheme."""

        STAAN_API_URL = "HTTPS://api.staan.ai"

    # Should not raise
    TestSettings().post_setup()


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
)
def test_plaintext_localhost_does_not_raise(url):
    """Plaintext localhost is exempted so a local mock can be used in development."""

    class TestSettings(Base):
        """Fake test settings with a plaintext localhost Staan URL."""

        STAAN_API_URL = url

    # Should not raise
    TestSettings().post_setup()


@pytest.mark.parametrize("max_snippets", [0, 11])
def test_out_of_range_max_snippets_raises(max_snippets):
    """The API only accepts 1 to 10 chunks per url, so a typo must fail at boot."""

    class TestSettings(Base):
        """Fake test settings with an out-of-range snippet limit."""

        STAAN_API_URL = "https://api.staan.ai"
        STAAN_MAX_SNIPPETS_PER_URL = max_snippets

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "STAAN_MAX_SNIPPETS_PER_URL" in str(excinfo.value)


@pytest.mark.parametrize("min_score", [-0.1, 1.5])
def test_out_of_range_min_snippet_score_raises(min_score):
    """The API only accepts a score between 0 and 1, so a typo must fail at boot."""

    class TestSettings(Base):
        """Fake test settings with an out-of-range snippet score."""

        STAAN_API_URL = "https://api.staan.ai"
        STAAN_MIN_SNIPPET_SCORE = min_score

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "STAAN_MIN_SNIPPET_SCORE" in str(excinfo.value)


def test_snippet_limits_are_not_checked_when_staan_is_disabled():
    """An unused out-of-range value must not block a deployment without Staan."""

    class TestSettings(Base):
        """Fake test settings with Staan disabled and a bogus snippet limit."""

        STAAN_API_URL = None
        STAAN_MAX_SNIPPETS_PER_URL = 50

    # Should not raise
    TestSettings().post_setup()


def test_unset_staan_url_does_not_raise():
    """STAAN_API_URL=None (default) must never raise: the tool is optional."""

    class TestSettings(Base):
        """Fake test settings with Staan disabled."""

        STAAN_API_URL = None

    # Should not raise
    TestSettings().post_setup()
