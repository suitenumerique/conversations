"""Test cases for the TitleGenerationAgent class."""

# pylint: disable=protected-access

import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from chat.agents.conversation import TitleGenerationAgent


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for the tests."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-XYZ"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"


def test_title_generation_agent_uses_default_model_hrid(settings):
    """Test that TitleGenerationAgent uses LLM_DEFAULT_MODEL_HRID from settings."""
    settings.AI_MODEL = "custom-llm-model"
    settings.AI_BASE_URL = "https://custom.api.com/v1/"
    settings.AI_API_KEY = "custom-key"
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"

    agent = TitleGenerationAgent()

    assert isinstance(agent._model, OpenAIChatModel)
    assert settings.LLM_CONFIGURATIONS["default-model"].model_name == "custom-llm-model"
    assert agent._model.model_name == "custom-llm-model"


def test_title_generation_agent_model_configuration():
    """Test that the agent model is properly configured."""
    agent = TitleGenerationAgent()

    assert isinstance(agent._model, OpenAIChatModel)
    assert agent._model.model_name == "model-XYZ"
    assert str(agent._model.client.base_url) == "https://api.llm.com/v1/"
    assert agent._model.client.api_key == "test-key"


def test_title_generation_agent_has_no_tools():
    """Test that TitleGenerationAgent has no tools configured."""
    agent = TitleGenerationAgent()

    assert agent._function_toolset.tools == {}
    assert not agent.get_tools()


def test_title_generation_agent_instructions():
    """Test that the agent instructions contain the system prompt."""
    agent = TitleGenerationAgent()

    # The agent should have the title generation system prompt as instructions
    instructions = agent._instructions
    assert len(instructions) == 1
    expected = (
        "You are a title generator. Your task is to create concise, descriptive titles "
        "that accurately summarize conversation content and help the user quickly identify the "
        "conversation.\n\n"
    )
    assert instructions[0] == expected
