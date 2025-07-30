"""Test cases for the _build_pydantic_agent function in the chat.clients.pydantic_ai module."""

# pylint:disable=protected-access
from django.core.exceptions import ImproperlyConfigured

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

from chat.clients.pydantic_ai import _build_pydantic_agent


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for the tests."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def test_build_pydantic_agent_success_no_tools():
    """Test successful agent creation without tools."""
    agent = _build_pydantic_agent([])
    assert isinstance(agent, Agent)

    assert agent._system_prompts == ("You are a helpful assistant",)
    assert agent._instructions is None
    assert isinstance(agent.model, OpenAIModel)
    assert agent.model.model_name == "model-123"
    assert str(agent.model.client.base_url) == "https://api.llm.com/v1/"
    assert agent.model.client.api_key == "test-key"
    assert agent._function_toolset.tools == {}


def test_build_pydantic_agent_with_tools(settings):
    """Test successful agent creation with tools."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    agent = _build_pydantic_agent([])
    assert isinstance(agent, Agent)

    assert agent._system_prompts == ("You are a helpful assistant",)
    assert agent._instructions is None
    assert isinstance(agent.model, OpenAIModel)
    assert agent.model.model_name == "model-123"
    assert str(agent.model.client.base_url) == "https://api.llm.com/v1/"
    assert agent.model.client.api_key == "test-key"
    assert list(agent._function_toolset.tools.keys()) == ["get_current_weather"]


def test_build_pydantic_agent_missing_base_url(settings):
    """Test agent creation fails with missing base URL."""
    settings.AI_BASE_URL = None

    with pytest.raises(ImproperlyConfigured, match="AIChatService configuration not set"):
        _build_pydantic_agent([])


def test_build_pydantic_agent_missing_api_key(settings):
    """Test agent creation fails with missing API key."""
    settings.AI_API_KEY = None

    with pytest.raises(ImproperlyConfigured, match="AIChatService configuration not set"):
        _build_pydantic_agent([])


def test_build_pydantic_agent_missing_model(settings):
    """Test agent creation fails with missing model."""
    settings.AI_MODEL = None

    with pytest.raises(ImproperlyConfigured, match="AIChatService configuration not set"):
        _build_pydantic_agent([])
