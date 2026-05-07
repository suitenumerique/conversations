"""Tests for the output token limit feature."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from openai import omit as OMIT
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, DeltaToolCall, FunctionModel
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.settings import ModelSettings

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProfile, LLMProvider
from conversations.settings import Base

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


def _length_stream_model(stream_function) -> FunctionModel:
    """Streaming FunctionModel whose response reports finish_reason='length'.

    FunctionModel never sets a finish_reason on its streamed response, so we
    wrap request_stream to stamp 'length' on it — mirroring what a real
    provider does when it hits the output token limit. Used to exercise the
    streaming path (production default), not the non-streaming one."""
    model = FunctionModel(stream_function=stream_function)
    request_stream = model.request_stream

    @asynccontextmanager
    async def _request_stream(*args, **kwargs):
        async with request_stream(*args, **kwargs) as streamed_response:
            streamed_response.finish_reason = "length"
            yield streamed_response

    model.request_stream = _request_stream
    return model


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------


def test_llm_max_output_tokens_per_message_default():
    """The cap is off by default: a deployment opts in once it knows its providers
    accept the parameter."""
    assert Base.LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE == 0


# ---------------------------------------------------------------------------
# Hook / flag tests
# ---------------------------------------------------------------------------


def test_last_finish_reason_initialized_to_none():
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
async def test_run_agent_sends_no_max_tokens_when_limit_disabled(settings, ui_messages):
    """LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE=0 disables the cap: no max_tokens is sent."""
    settings.LLM_MAX_OUTPUT_TOKENS_PER_MESSAGE = 0
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

    assert captured_kwargs["model_settings"] is None


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

    length_model = _length_stream_model(_model)

    chunks = []
    with service.conversation_agent.override(model=length_model):
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    annotation_chunks = [c for c in chunks if '"truncated"' in c]
    assert len(annotation_chunks) == 1


@pytest.mark.asyncio
async def test_truncation_flag_persisted_in_message_metadata(ui_messages):
    """The truncated flag must also survive on the stored message, since the banner
    is rendered from the persisted metadata after a reload, not from the stream."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _model(_messages: list[ModelMessage], _info: AgentInfo):
        yield "Hello world"

    length_model = _length_stream_model(_model)

    with service.conversation_agent.override(model=length_model):
        async for _ in service.stream_data_async(ui_messages):
            pass

    assert conversation.messages[-1].metadata["truncated"] is True


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
    assert "truncated" not in (conversation.messages[-1].metadata or {})


@pytest.mark.asyncio
async def test_truncation_before_any_text_shows_notice_not_error(ui_messages):
    """A reasoning model can spend the whole budget thinking. Pydantic AI then raises
    instead of returning; the user must get the truncation notice, not an error, and
    the empty response must stay out of the history sent back to the model."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _model(_messages: list[ModelMessage], _info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Let me think about this at length")}

    chunks = []
    with service.conversation_agent.override(model=_length_stream_model(_model)):
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    assert len([c for c in chunks if '"truncated"' in c]) == 1
    assert conversation.messages[-1].metadata["truncated"] is True
    assert not any(message["kind"] == "response" for message in conversation.pydantic_messages)


@pytest.mark.asyncio
async def test_truncation_before_any_text_keeps_streamed_message_id(ui_messages):
    """Pydantic AI raising skips the run's End node, where the streamed message id is
    normally handed over. The stored message must still carry it, not a fresh uuid."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _model(_messages: list[ModelMessage], _info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Let me think about this at length")}

    with service.conversation_agent.override(model=_length_stream_model(_model)):
        async for _chunk in service.stream_data_async(ui_messages):
            pass

    streamed_id = service._model_response_message_id  # pylint: disable=protected-access
    assert streamed_id
    assert conversation.messages[-1].id == streamed_id


@pytest.mark.asyncio
async def test_truncated_turn_replays_as_alternating_history(ui_messages):
    """A turn cut off before any text stores a question with no answer after it. The
    next turn must not send that question and the new one back to back: Mistral
    rejects the same role twice in a row."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _thinking_only(_messages: list[ModelMessage], _info: AgentInfo):
        yield {0: DeltaThinkingPart(content="Let me think about this at length")}

    with service.conversation_agent.override(model=_length_stream_model(_thinking_only)):
        async for _chunk in service.stream_data_async(ui_messages):
            pass

    replayed: list[list[ModelMessage]] = []

    async def _second_turn(messages: list[ModelMessage], _info: AgentInfo):
        replayed.append(messages)
        yield "Here is the answer."

    service = AIAgentService(conversation, user=conversation.owner)
    with service.conversation_agent.override(model=FunctionModel(stream_function=_second_turn)):
        async for _chunk in service.stream_data_async(ui_messages):
            pass

    # Flattened, because Pydantic AI folds the new prompt into the trailing request
    # rather than adding a message: the two questions then reach the provider as two
    # user messages all the same.
    part_kinds = [part.part_kind for message in replayed[0] for part in message.parts]
    assert all(
        not before == after == "user-prompt"
        for before, after in zip(part_kinds, part_kinds[1:], strict=False)
    ), part_kinds


@pytest.mark.asyncio
async def test_truncation_mid_tool_call_keeps_text_and_drops_tool_call(ui_messages):
    """Cut off mid-tool-call, the text written so far is kept but the tool call, which
    never ran, must not be stored: the next turn would send it without its return."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _model(_messages: list[ModelMessage], _info: AgentInfo):
        yield "Let me look that up."
        yield {1: DeltaToolCall(name="web_search", json_args='{"query": "unfinish')}

    chunks = []
    with service.conversation_agent.override(model=_length_stream_model(_model)):
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    assert len([c for c in chunks if '"truncated"' in c]) == 1
    assert conversation.messages[-1].metadata["truncated"] is True
    stored_response = conversation.pydantic_messages[-1]
    assert stored_response["kind"] == "response"
    assert [part["part_kind"] for part in stored_response["parts"]] == ["text"]
    assert stored_response["parts"][0]["content"] == "Let me look that up."


class _StopAtProvider(Exception):
    """Raised by the patched provider call, once its arguments are captured."""


@pytest.mark.asyncio
async def test_mistral_model_receives_max_tokens(settings, ui_messages):
    """A Mistral-kind model must get the cap as Mistral's `max_tokens` parameter."""
    settings.LLM_CONFIGURATIONS = {
        "mistral-model": LLModel(
            hrid="mistral-model",
            model_name="mistral-medium",
            human_readable_name="Mistral Medium",
            profile=None,
            provider=LLMProvider(
                hrid="mistral",
                kind="mistral",
                base_url="https://api.mistral.ai/v1",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "mistral-model"
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    model = service.conversation_agent._model  # pylint: disable=protected-access
    assert isinstance(model, MistralModel)

    with patch.object(
        model.client.chat, "stream_async", AsyncMock(side_effect=_StopAtProvider)
    ) as stream_async:
        with pytest.raises(_StopAtProvider):
            async for _ in service.stream_data_async(ui_messages):
                pass

    assert stream_async.call_args.kwargs["max_tokens"] == 1000


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (None, {"max_completion_tokens": 1000, "max_tokens": OMIT}),
        (
            LLMProfile(openai_chat_supports_max_completion_tokens=False),
            {"max_tokens": 1000, "max_completion_tokens": OMIT},
        ),
    ],
    ids=["default", "server-ignoring-max-completion-tokens"],
)
@pytest.mark.asyncio
async def test_openai_model_receives_the_cap_in_exactly_one_field(
    settings, ui_messages, profile, expected
):
    """An OpenAI-compatible model must get the cap in exactly one field: by default
    `max_completion_tokens`, and `max_tokens` for a server that ignores it (e.g. Albert
    serving Mistral). Never both: an etalab-hosted Mistral answers 422 when both are set."""
    settings.LLM_CONFIGURATIONS = {
        "albert-mistral": LLModel(
            hrid="albert-mistral",
            model_name="mistral-medium-2508",
            human_readable_name="Mistral Medium",
            profile=profile,
            provider=LLMProvider(
                hrid="albert",
                kind="openai",
                base_url="https://albert.api.etalab.gouv.fr/v1/",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "albert-mistral"
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    model = service.conversation_agent._model  # pylint: disable=protected-access

    with patch.object(
        model.client.chat.completions, "create", AsyncMock(side_effect=_StopAtProvider)
    ) as create:
        with pytest.raises(_StopAtProvider):
            async for _ in service.stream_data_async(ui_messages):
                pass

    for field, value in expected.items():
        assert create.call_args.kwargs[field] == value
