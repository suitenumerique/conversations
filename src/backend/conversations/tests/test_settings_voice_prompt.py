"""Tests for the voice prompt transcription settings validation in post_setup."""

import pytest

from chat.llm_configuration import LLModel
from conversations import settings as settings_module
from conversations.settings import Base


def test_unknown_transcription_hrid_raises():
    """A VOICE_PROMPT_TRANSCRIPTION_HRID missing from LLM_CONFIGURATIONS must fail at boot."""

    class TestSettings(Base):
        """Fake test settings pointing at a model entry that does not exist."""

        VOICE_PROMPT_TRANSCRIPTION_HRID = "missing-speech-model"

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "VOICE_PROMPT_TRANSCRIPTION_HRID" in str(excinfo.value)


def test_known_transcription_hrid_does_not_raise():
    """A VOICE_PROMPT_TRANSCRIPTION_HRID present in LLM_CONFIGURATIONS is accepted."""

    class TestSettings(Base):
        """Fake test settings pointing at an entry of the default configuration."""

        VOICE_PROMPT_TRANSCRIPTION_HRID = "default-model"

    TestSettings().post_setup()


def test_unset_transcription_hrid_does_not_raise():
    """Voice prompts are off by default, which needs no model entry."""

    class TestSettings(Base):
        """Fake test settings leaving VOICE_PROMPT_TRANSCRIPTION_HRID unset."""

    TestSettings().post_setup()


def test_transcription_hrid_without_provider_raises(monkeypatch):
    """The transcription endpoint calls the provider directly, so the entry needs one."""
    monkeypatch.setattr(
        settings_module,
        "load_llm_configuration",
        lambda _path: {
            "speech-model": LLModel(
                hrid="speech-model",
                model_name="mistral:voxtral",
                human_readable_name="Speech recognition",
                is_active=True,
                system_prompt="",
                tools=[],
            )
        },
    )

    class TestSettings(Base):
        """Fake test settings pointing at an entry with no provider."""

        VOICE_PROMPT_TRANSCRIPTION_HRID = "speech-model"

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "provider" in str(excinfo.value)
