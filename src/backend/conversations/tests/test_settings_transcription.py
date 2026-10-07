"""Tests for the voice prompt transcription settings validation in post_setup."""

import pytest

from conversations.settings import Base


def test_unknown_transcription_hrid_raises():
    """A TRANSCRIPTION_HRID missing from LLM_CONFIGURATIONS must fail at boot."""

    class TestSettings(Base):
        """Fake test settings pointing at a model entry that does not exist."""

        TRANSCRIPTION_HRID = "missing-speech-model"

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "TRANSCRIPTION_HRID" in str(excinfo.value)


def test_known_transcription_hrid_does_not_raise():
    """A TRANSCRIPTION_HRID present in LLM_CONFIGURATIONS is accepted."""

    class TestSettings(Base):
        """Fake test settings pointing at an entry of the default configuration."""

        TRANSCRIPTION_HRID = "default-model"

    TestSettings().post_setup()


def test_unset_transcription_hrid_does_not_raise():
    """Voice prompts are off by default, which needs no model entry."""

    class TestSettings(Base):
        """Fake test settings leaving TRANSCRIPTION_HRID unset."""

    TestSettings().post_setup()
