"""Unit tests for AIAgentService stream methods."""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async

from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for the tests."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """Fixture for test UI messages."""
    return [UIMessage(id="msg-1", role="user", content="Hello, how are you?", parts=[])]


@patch("chat.clients.pydantic_ai.convert_async_generator_to_sync")
def test_stream_text_delegates_to_async(mock_convert, ui_messages):
    """Test stream_text method delegates to async version."""
    conversation = ChatConversationFactory()
    service = AIAgentService(conversation, user=conversation.owner)
    mock_convert.return_value = iter(["Hello", " world"])

    result = service.stream_text(ui_messages, force_web_search=True)

    mock_convert.assert_called_once()
    assert result == mock_convert.return_value


@patch("chat.clients.pydantic_ai.convert_async_generator_to_sync")
def test_stream_data_delegates_to_async(mock_convert, ui_messages):
    """Test stream_data method delegates to async version."""
    conversation = ChatConversationFactory()
    service = AIAgentService(conversation, user=conversation.owner)
    mock_convert.return_value = iter(['0:"Hello"\n', 'd:{"finishReason":"stop"}\n'])

    result = service.stream_data(ui_messages, force_web_search=False)

    mock_convert.assert_called_once()
    assert result == mock_convert.return_value


@pytest.mark.asyncio
async def test_stream_text_async_filters_text_deltas(ui_messages):
    """Test stream_text_async only yields text deltas."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    # Mock _run_agent to return various delta types
    async def mock_run_agent(*args, **kwargs):
        yield events_v4.TextPart(text="Hello")
        yield events_v4.ToolCallStreamingStartPart(tool_call_id="123", tool_name="search")
        yield events_v4.TextPart(text=" world")
        yield events_v4.FinishMessagePart(
            finish_reason=events_v4.FinishReason.STOP,
            usage=events_v4.Usage(
                prompt_tokens=120,
                completion_tokens=456,
            ),
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_text_async(ui_messages):
            results.append(result)

        assert results == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_data_async_formats_as_sdk_events(ui_messages):
    """Test stream_data_async formats events correctly."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def mock_run_agent(*args, **kwargs):
        yield events_v4.TextPart(text="Hello")
        yield events_v4.FinishMessagePart(
            finish_reason=events_v4.FinishReason.STOP,
            usage=events_v4.Usage(
                prompt_tokens=120,
                completion_tokens=456,
            ),
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async(ui_messages):
            results.append(result)

        assert results == [
            '0:"Hello"\n',
            'd:{"finishReason":"stop","usage":{"promptTokens":120,"completionTokens":456}}\n',
        ]
