"""Fixtures for ConversationAgent behavioural eval tests."""

import pytest

from chat.agents.conversation import ConversationAgent
from chat.tools.descriptions import SELF_DOCUMENTATION_TOOL_DESCRIPTION
from chat.tests.evals.judge import create_judge, judge_response


@pytest.fixture(autouse=True)
def no_http_requests():
    """Allow real HTTP calls so that eval tests can reach the LLM API.

    This overrides the global no_http_requests fixture that blocks all outbound
    connections in the regular test suite.
    """


@pytest.fixture(name="conversation_agent")
def conversation_agent_fixture(settings):
    """Bare ConversationAgent with the real model and no extra tools."""
    return ConversationAgent(model_hrid=settings.LLM_DEFAULT_MODEL_HRID)


@pytest.fixture(name="self_doc_agent")
def self_doc_agent_fixture(settings):
    """ConversationAgent with the self_documentation tool registered.

    Mirrors what AIAgentService._setup_self_documentation_tool() does at runtime,
    but uses a lightweight in-memory payload so no DB access is needed.
    """
    agent = ConversationAgent(model_hrid=settings.LLM_DEFAULT_MODEL_HRID)

    @agent.instructions
    def self_documentation_instruction() -> str:
        return SELF_DOCUMENTATION_TOOL_DESCRIPTION

    @agent.tool_plain(name="self_documentation")
    async def self_documentation() -> dict:
        """Return assistant self-documentation metadata."""
        return {
            "model": settings.LLM_DEFAULT_MODEL_HRID,
            "capabilities": "text generation, document analysis",
            "privacy": "conversations are not shared outside your organisation",
        }

    return agent


@pytest.fixture(name="url_passthrough_agent")
def url_passthrough_agent_fixture(settings):
    """ConversationAgent with a deterministic fetch_resource tool.

    The tool always returns a fixed URL so the test can assert the URL
    appears in the model's response (Group D — URL passthrough).
    """
    agent = ConversationAgent(model_hrid=settings.LLM_DEFAULT_MODEL_HRID)

    @agent.tool_plain(name="fetch_resource")
    async def fetch_resource() -> str:
        """Fetch the URL of the requested resource and return it."""
        return "La ressource est disponible à : https://passthrough-eval.example.org/resource"

    return agent


@pytest.fixture(name="judge")
def judge_fixture(settings):
    """Return an async callable that judges a response against a rubric."""
    judge_agent = create_judge(model_hrid=settings.LLM_DEFAULT_MODEL_HRID)

    async def _judge(response_text: str, rubric: str):
        return await judge_response(response_text, rubric, judge_agent)

    return _judge
