"""Tests for the calculate tool and its registration on the agent."""
# pylint: disable=protected-access

import json
from unittest.mock import MagicMock

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.tools.calculate import calculate_expression

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Minimum settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def _ctx():
    ctx = MagicMock()
    ctx.retries = {}
    ctx.max_retries = 2
    ctx.tool_name = "calculate"
    return ctx


@pytest.mark.asyncio
async def test_tool_returns_expression_and_result():
    """The tool answers with the expression as written and the exact result."""
    assert await calculate_expression(_ctx(), "149.90 * 1.2") == "149.90 * 1.2 = 179.88"


@pytest.mark.asyncio
async def test_tool_asks_model_to_retry_on_invalid_expression():
    """An invalid expression becomes a ModelRetry carrying the fix hint."""
    with pytest.raises(ModelRetry, match="Use '.' as decimal separator"):
        await calculate_expression(_ctx(), "1 234,56 * 2")


def test_calculator_tool_is_registered_once():
    """The tool is registered for any conversation, once even if setup runs twice."""
    conversation = ChatConversationFactory()
    service = AIAgentService(conversation, user=conversation.owner)

    service._setup_calculator_tool()
    service._setup_calculator_tool()

    assert "calculate" in service.conversation_agent._function_toolset.tools


def test_conversation_turn_uses_calculate(api_client, mock_ai_agent_service):
    """End to end: the model calls calculate and receives the exact result."""
    conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=conversation.owner)
    tool_results = []

    async def agent_model(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            assert "calculate" in {tool.name for tool in info.function_tools}
            assert "call the calculate tool" in messages[0].instructions
            yield {
                0: DeltaToolCall(
                    name="calculate", json_args=json.dumps({"expression": "0.1 + 0.2"})
                )
            }
        else:
            last_request = messages[-1]
            assert isinstance(last_request, ModelRequest)
            tool_results.extend(
                part.content for part in last_request.parts if isinstance(part, ToolReturnPart)
            )
            yield "0.3"

    message = UIMessage(
        id="1",
        role="user",
        content="0.1 + 0.2 ?",
        parts=[TextUIPart(text="0.1 + 0.2 ?", type="text")],
    )
    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)  # NOSONAR
    assert tool_results == ["0.1 + 0.2 = 0.3"]
