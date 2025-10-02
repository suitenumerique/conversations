"""Tests for the BaseAgent class and its model initialization logic."""
# pylint: disable=protected-access

from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIChatModel

from chat.agents.base import BaseAgent
from chat.llm_configuration import LLModel, LLMProfile, LLMProvider


def test_not_custom_model(monkeypatch, settings):
    """Test that a model without a provider relies on Pydantic AI detection."""
    settings.LLM_CONFIGURATIONS = {
        "gpt-4": LLModel(
            hrid="gpt-4",
            model_name="openai:gpt-4",
            human_readable_name="GPT-4",
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }

    # Required for OpenAI models client initialization
    monkeypatch.setenv("OPENAI_API_KEY", "hello")

    agent = BaseAgent(model_hrid="gpt-4")
    assert isinstance(agent._model, OpenAIChatModel)


def test_custom_model_openai(settings):
    """Test that a custom OpenAI model is initialized correctly."""
    settings.LLM_CONFIGURATIONS = {
        "openai-compatible-model": LLModel(
            hrid="custom-gpt-4",
            model_name="gpt-4",
            human_readable_name="Custom GPT-4",
            profile=None,
            provider=LLMProvider(
                hrid="openai",
                kind="openai",
                base_url="https://test.vllm/v1",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }

    agent = BaseAgent(model_hrid="openai-compatible-model")
    assert isinstance(agent._model, OpenAIChatModel)


def test_custom_model_mistral(settings):
    """Test that a custom Mistral model is initialized correctly."""
    settings.LLM_CONFIGURATIONS = {
        "mistral-model": LLModel(
            hrid="mistral-model",
            model_name="mistral-7b-instruct-v0.1",
            human_readable_name="Mistral 7B Instruct",
            profile=None,
            provider=LLMProvider(
                hrid="mistral",
                kind="mistral",
                base_url="https://api.mistral.ai/v1",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }

    agent = BaseAgent(model_hrid="mistral-model")

    assert isinstance(agent._model, MistralModel)

    import pydantic_ai.models.mistral as mistral_models  # noqa: PLC0415 # pylint: disable=import-outside-toplevel

    assert mistral_models.__safe_map_patched__ is True  # pylint: disable=protected-access


def test_custom_model_openai_profile(settings):
    """Test that a custom OpenAI model with profile is initialized correctly."""
    settings.LLM_CONFIGURATIONS = {
        "openai-model": LLModel(
            hrid="openai-model",
            model_name="some-openai-model",
            human_readable_name="Some OpenAI Model",
            profile=LLMProfile(
                supports_json_schema_output=False,
                openai_supports_strict_tool_definition=False,
            ),
            provider=LLMProvider(
                hrid="openai",
                kind="openai",
                base_url="https://test.vllm/v1",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }

    agent = BaseAgent(model_hrid="openai-model")

    assert isinstance(agent._model, OpenAIChatModel)
    assert agent._model.profile.supports_tools is True
    assert agent._model.profile.supports_json_schema_output is False
    assert agent._model.profile.supports_json_object_output is True
