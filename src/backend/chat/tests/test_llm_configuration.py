"""Tests for llm_configuration module."""

import json

import django.conf

import pytest

from chat.llm_configuration import (
    LLMConfiguration,
    LLModel,
    LLMProvider,
    _get_setting_or_env_or_value,
    conversation_message_token_budget,
    load_llm_configuration,
    usable_token_context,
)


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up environment variables and Django settings for the tests."""
    monkeypatch.setenv("TEST_ENV_VAR", "env_value")
    monkeypatch.setattr(django.conf.settings, "TEST_SETTING", "setting_value", raising=False)


def test_get_setting_or_env_or_value_env(monkeypatch):
    """Test retrieving value from environment variable."""
    monkeypatch.setenv("MY_ENV", "my_env_value")
    assert _get_setting_or_env_or_value("environ.MY_ENV") == "my_env_value"


def test_get_setting_or_env_or_value_setting(monkeypatch):
    """Test retrieving value from Django settings."""
    monkeypatch.setattr(django.conf.settings, "MY_SETTING", "my_setting_value", raising=False)
    assert _get_setting_or_env_or_value("settings.MY_SETTING") == "my_setting_value"


def test_get_setting_or_env_or_value_direct():
    """Test returning direct value."""
    assert _get_setting_or_env_or_value("direct_value") == "direct_value"


def test_get_setting_or_env_or_value_env_missing():
    """Test error when environment variable is missing."""
    with pytest.raises(ValueError):
        _get_setting_or_env_or_value("environ.NOT_SET_ENV")


def test_get_setting_or_env_or_value_setting_missing():
    """Test error when Django setting is missing."""
    with pytest.raises(ValueError):
        _get_setting_or_env_or_value("settings.NOT_SET_SETTING")


def test_llmprovider_model_valid():
    """Test LLMProvider with valid environment and setting values."""
    provider = LLMProvider(
        hrid="openai",
        base_url="environ.TEST_ENV_VAR",
        api_key="settings.TEST_SETTING",
    )
    assert provider.base_url == "env_value"
    assert provider.api_key == "setting_value"


def test_llmodel_provider_name_and_provider_exclusive():
    """Test that provider_name and provider are mutually exclusive."""
    provider = LLMProvider(hrid="openai", base_url="direct", api_key="direct")
    with pytest.raises(ValueError):
        LLModel(
            hrid="gpt-4",
            model_name="gpt-4",
            human_readable_name="GPT-4",
            provider_name="openai",
            provider=provider,
            is_active=True,
            system_prompt="direct",
            tools=[],
        )


def test_llmodel_model_name_format():
    """Test that model_name with provider prefix is accepted without provider_name."""
    model = LLModel(
        hrid="gpt-4",
        model_name="openai:gpt-4",
        human_readable_name="GPT-4",
        is_active=True,
        system_prompt="direct",
        tools=[],
    )
    assert model.model_name == "openai:gpt-4"


def test_llmodel_missing_provider_and_wrong_model_name():
    """
    Test error when both provider_name and provider are missing and model_name is not prefixed.
    """
    with pytest.raises(ValueError):
        LLModel(
            hrid="gpt-4",
            model_name="gpt4",
            human_readable_name="GPT-4",
            is_active=True,
            system_prompt="direct",
            tools=[],
        )


def test_llmconfiguration_fill_providers_success():
    """Test successful filling of providers in LLMConfiguration."""
    provider = LLMProvider(hrid="openai", base_url="direct", api_key="direct")
    model = LLModel(
        hrid="gpt-4",
        model_name="gpt-4",
        human_readable_name="GPT-4",
        provider_name="openai",
        is_active=True,
        system_prompt="direct",
        tools=[],
    )
    config = LLMConfiguration(models=[model], providers=[provider])
    assert config.models[0].provider == provider


def test_llmconfiguration_fill_providers_missing():
    """Test error when provider_name does not match any provider in LLMConfiguration."""
    model = LLModel(
        hrid="gpt-4",
        model_name="gpt-4",
        human_readable_name="GPT-4",
        provider_name="notfound",
        is_active=True,
        system_prompt="direct",
        tools=[],
    )
    with pytest.raises(ValueError):
        LLMConfiguration(models=[model], providers=[])


def test_load_llm_configuration(tmp_path, monkeypatch):
    """Test loading LLM configuration from JSON file with env and settings."""
    monkeypatch.setenv("TEST_ENV_VAR", "env_value")
    monkeypatch.setattr(django.conf.settings, "TEST_SETTING", "setting_value", raising=False)
    config_dict = {
        "models": [
            {
                "hrid": "gpt-4",
                "model_name": "gpt-4",
                "human_readable_name": "GPT-4",
                "provider_name": "openai",
                "is_active": True,
                "system_prompt": "direct",
                "tools": [],
            }
        ],
        "providers": [
            {
                "hrid": "openai",
                "base_url": "environ.TEST_ENV_VAR",
                "api_key": "settings.TEST_SETTING",
            }
        ],
    }
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(json.dumps(config_dict), encoding="utf-8")
    model_map = load_llm_configuration(str(config_path))
    assert "gpt-4" in model_map
    assert model_map["gpt-4"].provider.base_url == "env_value"
    assert model_map["gpt-4"].provider.api_key == "setting_value"


def test_llmodel_is_custom_property():
    """Test the is_custom property of LLModel."""
    provider = LLMProvider(hrid="custom", base_url="direct", api_key="direct")
    custom_model = LLModel(
        hrid="custom-model",
        model_name="custom-model",
        human_readable_name="Custom Model",
        provider=provider,
        is_active=True,
        system_prompt="direct",
        tools=[],
    )
    non_custom_model = LLModel(
        hrid="prefixed-model",
        model_name="openai:prefixed-model",
        human_readable_name="Prefixed Model",
        is_active=True,
        system_prompt="direct",
        tools=[],
    )
    assert custom_model.is_custom is True
    assert non_custom_model.is_custom is False


def test_llm_profile_concatenate_instruction_messages_from_json():
    """LLMProfile parses concatenate_instruction_messages from JSON config."""
    config_json = json.dumps(
        {
            "models": [
                {
                    "hrid": "vllm-model",
                    "model_name": "my-model",
                    "human_readable_name": "My Model",
                    "concatenate_instruction_messages": True,
                    "provider": {
                        "hrid": "my-provider",
                        "base_url": "https://vllm.example.com/v1",
                        "api_key": "testkey",
                    },
                    "is_active": True,
                    "system_prompt": "You are helpful.",
                    "tools": [],
                }
            ],
            "providers": [
                {
                    "hrid": "my-provider",
                    "base_url": "https://vllm.example.com/v1",
                    "api_key": "testkey",
                }
            ],
        }
    )
    config = LLMConfiguration.model_validate_json(config_json)
    assert config.models[0].concatenate_instruction_messages is True


def test_llmodel_max_token_context_parses_string():
    """Test max_token_context accepts string values from JSON config."""
    model = LLModel(
        hrid="gpt-4",
        model_name="openai:gpt-4",
        human_readable_name="GPT-4",
        is_active=True,
        system_prompt="direct",
        tools=[],
        max_token_context="128000",
    )
    assert model.max_token_context == 128000


def test_llmodel_max_token_context_rejects_invalid_value():
    """Test max_token_context rejects non integer-like values."""
    with pytest.raises(ValueError):
        LLModel(
            hrid="gpt-4",
            model_name="openai:gpt-4",
            human_readable_name="GPT-4",
            is_active=True,
            system_prompt="direct",
            tools=[],
            max_token_context="abc",
        )


def test_usable_token_context_subtracts_security_buffer(settings):
    """usable_token_context = max_token_context - security buffer, floored at 0."""
    settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS = 10000
    model = LLModel(
        hrid="m",
        model_name="m",
        human_readable_name="M",
        is_active=True,
        icon=None,
        system_prompt="",
        tools=[],
        max_token_context=128000,
        provider=LLMProvider(hrid="p", base_url="https://example.com", api_key="k"),
    )
    assert usable_token_context(model) == 118000


def test_usable_token_context_is_zero_without_max_token_context(settings):
    """Returns 0 when the model has no max_token_context configured."""
    settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS = 10000
    model = LLModel(
        hrid="m",
        model_name="m",
        human_readable_name="M",
        is_active=True,
        icon=None,
        system_prompt="",
        tools=[],
        max_token_context=None,
        provider=LLMProvider(hrid="p", base_url="https://example.com", api_key="k"),
    )
    assert usable_token_context(model) == 0


def test_conversation_message_token_budget_uses_history_share(settings):
    """History budget = (1 - ratio) x usable context."""
    settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS = 10000
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.5
    model = LLModel(
        hrid="m",
        model_name="m",
        human_readable_name="M",
        is_active=True,
        icon=None,
        system_prompt="",
        tools=[],
        max_token_context=128000,
        provider=LLMProvider(hrid="p", base_url="https://example.com", api_key="k"),
    )
    assert conversation_message_token_budget(model) == 59000
