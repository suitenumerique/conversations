"""Unit tests for AIAgentService stream methods."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from asgiref.sync import sync_to_async
from mistralai.client.errors import HTTPValidationError, HTTPValidationErrorData, SDKError
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db()


class AsyncRaiseIterator:
    """Async iterator that raises the given exception on the first iteration."""

    def __init__(self, exc):
        self.exc = exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self.exc


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
                co2_impact=0.0,
            ),
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async(ui_messages):
            results.append(result)

        assert results == [
            '0:"Hello"\n',
            'd:{"finishReason":"stop","usage":{"promptTokens":120,"completionTokens":456,'
            '"co2Impact":0.0}}\n',
        ]


@pytest.mark.asyncio
async def test_stream_data_async_emits_model_busy_on_503():
    """503 ModelHTTPError emits model_busy ErrorPart."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ModelHTTPError(status_code=503, model_name="test-model"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async([]):
            results.append(result)

    assert results == ['3:"model_busy"\n']


@pytest.mark.asyncio
async def test_stream_data_async_emits_model_unavailable_on_5xx():
    """Generic 5xx ModelHTTPError emits model_unavailable ErrorPart."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ModelHTTPError(status_code=500, model_name="test-model"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async([]):
            results.append(result)

    assert results == ['3:"model_unavailable"\n']


@pytest.mark.asyncio
async def test_stream_data_async_emits_model_rate_limited_on_429():
    """429 ModelHTTPError emits model_rate_limited ErrorPart."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ModelHTTPError(status_code=429, model_name="test-model"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async([]):
            results.append(result)

    assert results == ['3:"model_rate_limited"\n']


@pytest.mark.asyncio
async def test_stream_data_async_emits_model_connection_error_on_api_error():
    """ModelAPIError (e.g. connection refused) emits model_connection_error ErrorPart."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(
            ModelAPIError(model_name="test-model", message="Connection error.")
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async([]):
            results.append(result)

    assert results == ['3:"model_connection_error"\n']


@pytest.mark.asyncio
async def test_stream_data_async_emits_model_busy_on_sdk_error_503():
    """Mistral SDKError with 503 emits model_busy ErrorPart."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.text = ""
    mock_response.headers = httpx.Headers()

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(
            SDKError(message="service unavailable", raw_response=mock_response)
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async([]):
            results.append(result)

    assert results == ['3:"model_busy"\n']


@pytest.mark.asyncio
async def test_stream_data_async_emits_model_wrong_type_on_http_validation_error_422():
    """Mistral HTTPValidationError with 422 emits model_wrong_type ErrorPart."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 422
    mock_response.text = ""
    mock_response.headers = httpx.Headers()

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(
            HTTPValidationError(data=HTTPValidationErrorData(), raw_response=mock_response)
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        results = []
        async for result in service.stream_data_async([]):
            results.append(result)

    assert results == ['3:"model_wrong_type"\n']


@pytest.mark.asyncio
async def test_stream_data_async_reraises_unknown_exceptions():
    """Unknown exceptions are not swallowed — they propagate."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ValueError("unexpected"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        with pytest.raises(ValueError, match="unexpected"):
            async for _ in service.stream_data_async([]):
                pass


@pytest.mark.asyncio
async def test_stream_text_async_reraises_http_error():
    """ModelHTTPError is re-raised on text protocol path
    (encode_text returns None for ErrorPart)."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ModelHTTPError(status_code=503, model_name="test-model"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        with pytest.raises(ModelHTTPError):
            async for _ in service.stream_text_async([]):
                pass


@pytest.mark.asyncio
async def test_stream_text_async_reraises_connection_error():
    """ModelAPIError is re-raised on text protocol path (encode_text returns None for ErrorPart)."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(
            ModelAPIError(model_name="test-model", message="Connection error.")
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        with pytest.raises(ModelAPIError):
            async for _ in service.stream_text_async([]):
                pass


@pytest.mark.asyncio
async def test_stream_data_async_persists_user_message_on_http_error(ui_messages):
    """On LLM provider error, the user message is saved to conversation.messages."""
    conversation = await sync_to_async(ChatConversationFactory)()
    assert conversation.messages == []

    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ModelHTTPError(status_code=503, model_name="test-model"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        async for _ in service.stream_data_async(ui_messages):
            pass

    await sync_to_async(conversation.refresh_from_db)()
    assert len(conversation.messages) == 1
    assert conversation.messages[0].role == "user"
    assert conversation.messages[0].id == ui_messages[0].id


@pytest.mark.asyncio
async def test_stream_data_async_persists_user_message_on_connection_error(ui_messages):
    """On ModelAPIError, the user message is saved to conversation.messages."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(
            ModelAPIError(model_name="test-model", message="Connection error.")
        )

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        async for _ in service.stream_data_async(ui_messages):
            pass

    await sync_to_async(conversation.refresh_from_db)()
    assert len(conversation.messages) == 1
    assert conversation.messages[0].role == "user"


@pytest.mark.asyncio
async def test_stream_data_async_does_not_duplicate_user_message_on_repeated_error(ui_messages):
    """Repeated errors with the same message do not accumulate duplicates."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    def mock_run_agent(*args, **kwargs):
        return AsyncRaiseIterator(ModelHTTPError(status_code=503, model_name="test-model"))

    with patch.object(service, "_run_agent", side_effect=mock_run_agent):
        async for _ in service.stream_data_async(ui_messages):
            pass
        async for _ in service.stream_data_async(ui_messages):
            pass

    await sync_to_async(conversation.refresh_from_db)()
    assert len(conversation.messages) == 1
