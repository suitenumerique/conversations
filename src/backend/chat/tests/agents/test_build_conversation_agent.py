"""Test cases for the ConversationAgent class in the chat.clients.pydantic_ai module."""

# pylint:disable=protected-access

import logging

import pytest
from freezegun import freeze_time
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from chat.agents.conversation import ConversationAgent
from chat.llm_configuration import LLModel, LLMProvider


def assert_base_instructions(instructions, date_str=None, language_str=""):
    """Assert the standard set of ConversationAgent instructions are registered."""
    assert len(instructions) == 4
    assert instructions[0] == "You are a helpful assistant"
    assert instructions[1].__name__ == "add_the_date"
    if date_str is not None:
        assert instructions[1]() == date_str
    assert instructions[2].__name__ == "enforce_response_language"
    assert instructions[2]() == language_str
    assert instructions[3].__name__ == "prevent_url_hallucination"
    assert "Never invent or guess URLs" in instructions[3]()


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
    assert agent._system_prompts == ()

    assert_base_instructions(agent._instructions)

    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "model-123"
    assert str(agent.model.client.base_url) == "https://api.llm.com/v1/"
    assert agent.model.client.api_key == "test-key"
    assert agent._function_toolset.tools == {}


@freeze_time("2025-07-25T10:36:35.297675Z")
def test_build_pydantic_agent_with_tools(settings):
    """Test successful agent creation with tools."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    agent = ConversationAgent(model_hrid="default-model")
    assert isinstance(agent, Agent)

    assert_base_instructions(agent._instructions, date_str="Today is Friday 25/07/2025.")

    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "model-123"
    assert str(agent.model.client.base_url) == "https://api.llm.com/v1/"
    assert agent.model.client.api_key == "test-key"
    assert list(agent._function_toolset.tools.keys()) == ["get_current_weather"]


@freeze_time("2025-07-25T10:36:35.297675Z")
def test_add_dynamic_system_prompt():
    """
    Ensure add_the_date and enforce_response_language instructions are registered
    and returns proper values.
    """
    agent = ConversationAgent(model_hrid="default-model")

    assert len(agent._system_prompt_functions) == 0

    assert_base_instructions(agent._instructions, date_str="Today is Friday 25/07/2025.")

    agent = ConversationAgent(model_hrid="default-model", language="fr-fr")
    assert agent._instructions[2]() == "Answer in french."


def test_agent_is_web_search_configured():
    """Test whether web search backend is configured on the model."""
    agent = ConversationAgent(model_hrid="default-model")
    assert agent.is_web_search_configured() is False


def test_agent_is_web_search_configured_when_defined_in_model_config(settings):
    """Web search is configured when LLModel.web_search is set."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="model-123",
            human_readable_name="Default Model",
            is_active=True,
            icon=None,
            system_prompt="You are a helpful assistant",
            tools=[],
            web_search="chat.tools.web_search_brave.web_search_brave_llm_context",
            provider=LLMProvider(
                hrid="default-provider",
                base_url="https://api.llm.com/v1/",
                api_key="test-key",
            ),
        ),
    }
    agent = ConversationAgent(model_hrid="default-model")
    assert agent.is_web_search_configured() is True


@freeze_time("2025-07-25T10:36:35.297675Z")
@pytest.mark.parametrize(
    "legacy_tool",
    [
        "web_search_brave",
        "web_search_brave_with_document_backend",
        "web_search_tavily",
        "web_search_albert_rag",
    ],
)
def test_build_pydantic_agent_with_legacy_tools(settings, caplog, legacy_tool):
    """Test successful agent creation when obsolete tools are used."""
    settings.AI_AGENT_TOOLS = [legacy_tool]
    with caplog.at_level(logging.WARNING, logger="chat.llm_configuration"):
        agent = ConversationAgent(model_hrid="default-model")
    assert "Ignoring legacy tool(s)" in caplog.text
    assert isinstance(agent, Agent)

    assert_base_instructions(agent._instructions, date_str="Today is Friday 25/07/2025.")

    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "model-123"
    assert str(agent.model.client.base_url) == "https://api.llm.com/v1/"
    assert agent.model.client.api_key == "test-key"
    assert not list(agent._function_toolset.tools.keys())
