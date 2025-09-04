"""Test cases for the _build_pydantic_agent function in the chat.clients.pydantic_ai module."""

# pylint:disable=protected-access

import pytest
from freezegun import freeze_time
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

    # Unused settings but required for initialization
    settings.AI_ROUTING_MODEL = ""
    settings.AI_ROUTING_MODEL_BASE_URL = ""
    settings.AI_ROUTING_MODEL_API_KEY = ""


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


@freeze_time("2025-07-25T10:36:35.297675Z")
def test_add_dynamic_system_prompt():
    """
    Ensure add_the_date and enforce_response_language system prompt are registered
    and returns proper values.
    """
    agent = _build_pydantic_agent([])

    assert len(agent._system_prompt_functions) == 2

    assert agent._system_prompt_functions[0].function.__name__ == "add_the_date"
    assert agent._system_prompt_functions[0].function() == "Today is Friday 25/07/2025."

    assert agent._system_prompt_functions[1].function.__name__ == "enforce_response_language"
    assert agent._system_prompt_functions[1].function() == ""

    agent = _build_pydantic_agent([], language="fr-fr")
    assert agent._system_prompt_functions[1].function() == "Answer in french."
