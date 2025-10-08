"""Test cases for the ConversationAgent class in the chat.clients.pydantic_ai module."""

# pylint:disable=protected-access

import pytest
import responses
from freezegun import freeze_time
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from chat.agents.conversation import ConversationAgent
from chat.clients.pydantic_ai import ContextDeps


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
    agent = ConversationAgent(model_hrid="default-model")
    assert isinstance(agent, Agent)

    assert agent._system_prompts == ("You are a helpful assistant",)
    assert agent._instructions == []
    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "model-123"
    assert str(agent.model.client.base_url) == "https://api.llm.com/v1/"
    assert agent.model.client.api_key == "test-key"
    assert agent._function_toolset.tools == {}


def test_build_pydantic_agent_with_tools(settings):
    """Test successful agent creation with tools."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    agent = ConversationAgent(model_hrid="default-model")
    assert isinstance(agent, Agent)

    assert agent._system_prompts == ("You are a helpful assistant",)
    assert agent._instructions == []
    assert isinstance(agent.model, OpenAIChatModel)
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
    agent = ConversationAgent(model_hrid="default-model")

    assert len(agent._system_prompt_functions) == 2

    assert agent._system_prompt_functions[0].function.__name__ == "add_the_date"
    assert agent._system_prompt_functions[0].function() == "Today is Friday 25/07/2025."

    assert agent._system_prompt_functions[1].function.__name__ == "enforce_response_language"
    assert agent._system_prompt_functions[1].function() == ""

    agent = ConversationAgent(model_hrid="default-model", language="fr-fr")
    assert agent._system_prompt_functions[1].function() == "Answer in french."


def test_agent_get_web_search_tool_name(settings):
    """Test the web_search_available method."""
    settings.AI_AGENT_TOOLS = ["get_current_weather", "web_search_albert_rag"]
    agent = ConversationAgent(model_hrid="default-model")
    assert agent.get_web_search_tool_name() == "web_search_albert_rag"

    settings.AI_AGENT_TOOLS = ["get_current_weather"]
    agent = ConversationAgent(model_hrid="default-model")
    assert agent.get_web_search_tool_name() is None

    settings.AI_AGENT_TOOLS = ["get_current_weather", "web_search_tavily", "web_search_albert_rag"]
    agent = ConversationAgent(model_hrid="default-model")
    assert agent.get_web_search_tool_name() == "web_search_tavily"


@responses.activate
def test_web_search_tool_avalability(settings):
    """Test the web search tool availability according to context."""
    responses.add(
        responses.POST,
        "https://api.tavily.com/search",
        json={"results": []},
        status=200,
    )
    context_deps = ContextDeps(conversation=None, user=None, web_search_enabled=True)

    # No tools (context allows web search, but no tool configured)
    agent = ConversationAgent(model_hrid="default-model")
    with agent.override(model=TestModel(), deps=context_deps):
        response = agent.run_sync("What tools do you have?")
        assert response.output == "success (no tool calls)"

    # Tool configured, context allows web search
    settings.AI_AGENT_TOOLS = ["web_search_tavily"]
    agent = ConversationAgent(model_hrid="default-model")  # re-init to pick up new settings
    with agent.override(model=TestModel(), deps=context_deps):
        response = agent.run_sync("What tools do you have?")
        assert response.output == '{"web_search_tavily":[]}'

    # Tool configured, context disables web search
    context_deps.web_search_enabled = False
    with agent.override(model=TestModel(), deps=context_deps):
        response = agent.run_sync("What tools do you have?")
        assert response.output == "success (no tool calls)"
