"""Tests for the Staan settings validation in post_setup."""

import pytest

from conversations.settings import Base


@pytest.mark.parametrize("max_snippets", [0, 11])
def test_out_of_range_max_snippets_raises(max_snippets):
    """The API only accepts 1 to 10 chunks per url, so a typo must fail at boot."""

    class TestSettings(Base):
        """Fake test settings with an out-of-range snippet limit."""

        STAAN_MAX_SNIPPETS_PER_URL = max_snippets

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "STAAN_MAX_SNIPPETS_PER_URL" in str(excinfo.value)


@pytest.mark.parametrize("min_score", [-0.1, 1.5])
def test_out_of_range_min_snippet_score_raises(min_score):
    """The API only accepts a score between 0 and 1, so a typo must fail at boot."""

    class TestSettings(Base):
        """Fake test settings with an out-of-range snippet score."""

        STAAN_MIN_SNIPPET_SCORE = min_score

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "STAAN_MIN_SNIPPET_SCORE" in str(excinfo.value)


def test_default_snippet_limits_do_not_raise():
    """The shipped defaults must be inside the range the API accepts."""

    class TestSettings(Base):
        """Fake test settings leaving every Staan value at its default."""

    # Should not raise
    TestSettings().post_setup()
