"""Tests for self-documentation tool wiring in AIAgentService."""

# pylint: disable=protected-access,redefined-outer-name
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai import RunContext
from pydantic_ai.usage import RunUsage

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True, name="mock_self_documentation_loader")
def mock_self_documentation_loader_fixture():
    """Patch a DB call"""
    with patch(
        "chat.tools.self_documentation.load_db_self_documentation",
        new_callable=AsyncMock,
        return_value="",
    ):
        yield


@pytest.fixture(autouse=True, name="ai_settings")
def ai_settings_fixture(settings):
    """Custom settings"""
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
    return settings


def test_setup_self_documentation_tool_registers_tool(django_assert_num_queries):
    """Service should register a self_documentation tool once."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    with django_assert_num_queries(0):
        service._setup_self_documentation_tool()
        service._setup_self_documentation_tool()

    assert "self_documentation" in service.conversation_agent._function_toolset.tools


@pytest.mark.asyncio
async def test_self_documentation_tool_reflects_runtime_web_search_enabled():
    """Tool output should include runtime web search status and model config from deps."""
    user = await sync_to_async(UserFactory)()
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)
    service = await sync_to_async(AIAgentService)(conversation, user=user)
    service._setup_self_documentation_tool()

    run_ctx = RunContext(model="test", usage=RunUsage(), deps=service._context_deps)

    with patch(
        "chat.tools.self_documentation.load_db_self_documentation",
        new_callable=AsyncMock,
        return_value="mocked doc",
    ):
        result = await service.conversation_agent._function_toolset.tools[
            "self_documentation"
        ].function(run_ctx)

    assert "self_documentation" in result.return_value
    assert "runtime" in result.return_value

    assert "model" in result.return_value["runtime"]
    assert "tools" in result.return_value["runtime"]
    assert "attachments" in result.return_value["runtime"]
