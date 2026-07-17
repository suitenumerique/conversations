"""Tests for the output token limit feature."""

from contextlib import asynccontextmanager
from unittest.mock import patch

from django.conf import settings as django_settings

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for all tests in this module."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []
    settings.LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE = 1000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """Fixture providing a single user UIMessage."""
    return [
        UIMessage(
            id="msg-1",
            role="user",
            content="Hello",
            parts=[TextUIPart(type="text", text="Hello")],
        )
    ]


@pytest.fixture(name="simple_model")
def simple_model_fixture():
    """Fixture providing a simple streaming FunctionModel."""

    async def _model(_messages: list[ModelMessage], _info: AgentInfo):
        yield "Hello world"

    return FunctionModel(stream_function=_model)


class _LengthStreamFunctionModel(FunctionModel):
    """Streaming FunctionModel whose response reports finish_reason='length'.

    FunctionModel never sets a finish_reason on its streamed response, so we
    override request_stream to stamp 'length' on it — mirroring what a real
    provider does when it hits the output token limit. Used to exercise the
    streaming path (production default), not the non-streaming one."""

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs):
        async with super().request_stream(*args, **kwargs) as streamed_response:
            streamed_response.finish_reason = "length"
            yield streamed_response


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------


def test_llm_max_output_tokens_per_message_setting_exists():
    """Setting must exist with a positive integer value."""
    assert hasattr(django_settings, "LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE")
    assert isinstance(django_settings.LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE, int)
    assert django_settings.LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE == 1000


# ---------------------------------------------------------------------------
# Hook / flag tests
# ---------------------------------------------------------------------------


def test_response_truncated_flag_initialized_to_false():
    """AIAgentService must start with _last_finish_reason=None."""
    conversation = ChatConversationFactory()
    service = AIAgentService(conversation, user=conversation.owner)
    assert service._last_finish_reason is None  # pylint: disable=protected-access


@pytest.mark.asyncio
async def test_response_truncated_flag_reset_by_clean():
    """_clean() must reset _last_finish_reason to None."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    service._last_finish_reason = "length"  # pylint: disable=protected-access
    await service._clean()  # pylint: disable=protected-access
    assert service._last_finish_reason is None  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# Stream event tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_passes_max_tokens_model_settings(ui_messages):
    """_run_agent must pass
    ModelSettings(max_tokens=LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE) to agent.iter()."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    captured_kwargs = {}
    original_iter = service.conversation_agent.iter

    def capturing_iter(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_iter(*args, **kwargs)

    async def simple_model(_messages: list[ModelMessage], _info: AgentInfo):
        yield "ok"

    with service.conversation_agent.override(model=FunctionModel(stream_function=simple_model)):
        with patch.object(service.conversation_agent, "iter", side_effect=capturing_iter):
            async for _ in service.stream_data_async(ui_messages):
                pass

    assert "model_settings" in captured_kwargs
    assert captured_kwargs["model_settings"] == ModelSettings(max_tokens=1000)


@pytest.mark.asyncio
async def test_truncation_annotation_emitted_when_flag_is_set(ui_messages):
    """When the model returns finish_reason='length', stream must emit
    MessageAnnotationPart with truncated=True."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    service._support_streaming = False  # pylint: disable=protected-access

    def _length_model(_messages: list[ModelMessage], _info: AgentInfo):
        return ModelResponse(parts=[TextPart(content="Hello world")], finish_reason="length")

    length_model = FunctionModel(function=_length_model)

    chunks = []
    with service.conversation_agent.override(model=length_model):
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    # The MessageAnnotationPart is encoded as a line containing '"truncated"'
    annotation_chunks = [c for c in chunks if '"truncated"' in c]
    assert len(annotation_chunks) == 1
    assert '"truncated"' in annotation_chunks[0]


@pytest.mark.asyncio
async def test_truncation_annotation_emitted_on_streaming_path(ui_messages):
    """On the streaming path (production default, _support_streaming=True), a
    response finishing with finish_reason='length' must trigger the truncated
    annotation. This covers the after_model_request hook firing on agent.iter's
    streaming branch, which the non-streaming test above does not exercise."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    assert service._support_streaming is True  # pylint: disable=protected-access

    async def _model(_messages: list[ModelMessage], _info: AgentInfo):
        yield "Hello world"

    length_model = _LengthStreamFunctionModel(stream_function=_model)

    chunks = []
    with service.conversation_agent.override(model=length_model):
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    annotation_chunks = [c for c in chunks if '"truncated"' in c]
    assert len(annotation_chunks) == 1


@pytest.mark.asyncio
async def test_truncation_annotation_not_emitted_when_flag_is_false(ui_messages, simple_model):
    """When _last_finish_reason is not 'length', stream must NOT emit a truncation annotation."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    chunks = []
    with service.conversation_agent.override(model=simple_model):
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    annotation_chunks = [c for c in chunks if '"truncated"' in c]
    assert len(annotation_chunks) == 0
