"""Tests for self-documentation tool wiring in AIAgentService."""

# pylint: disable=protected-access,redefined-outer-name

from pydantic_ai import RunContext
from pydantic_ai.usage import RunUsage
import pytest

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings

pytestmark = pytest.mark.django_db()


def test_setup_self_documentation_tool_registers_tool(settings, django_assert_num_queries):
    """Service should register a self_documentation tool once."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="provider/model",
            human_readable_name="Provider Model",
            is_active=True,
            icon=None,
            system_prompt="You are an assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="provider",
                base_url="https://example.com",
                api_key="key",
                kind="openai",
            ),
            settings=LLMSettings(max_tokens=1024),
        )
    }
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    with django_assert_num_queries(0):
        service._setup_self_documentation_tool()
        service._setup_self_documentation_tool()

    assert "self_documentation" in service.conversation_agent._function_toolset.tools


def test_self_documentation_tool_reflects_runtime_web_search_enabled(settings):
    """Tool output should include runtime web search status from deps."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="provider/model",
            human_readable_name="Provider Model",
            is_active=True,
            icon=None,
            system_prompt="You are an assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="provider",
                base_url="https://example.com",
                api_key="key",
                kind="openai",
            ),
            settings=LLMSettings(max_tokens=1024),
        )
    }
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)
    service._setup_self_documentation_tool()

    run_ctx = RunContext(model="test", usage=RunUsage(), deps=service._context_deps)
    result = service.conversation_agent._function_toolset.tools["self_documentation"].function(run_ctx)

    assert (
        result.return_value["runtime"]["features"]["web_search_runtime_enabled"]
        == service._context_deps.web_search_enabled
    )
    assert result.return_value["runtime"]["model"]["max_tokens"] == 1024
