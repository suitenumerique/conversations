"""The turn is persisted when a stream is interrupted, for both triggers.

The model is stubbed at the model layer (FunctionModel) rather than by
patching the agent run: the partial response is captured by the Pydantic AI
graph itself, so a test that patched the run would prove nothing about it.
"""
# pylint: disable=protected-access  # tests drive the service's stop-check clock

import asyncio
import json

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.exceptions import StreamCancelException
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.tests.utils import stream_frames

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def mock_token_counter(monkeypatch):
    """Prevent tiktoken from making network calls during history token estimation."""
    monkeypatch.setattr(
        "chat.agents.history_processors.count_approx_tokens",
        lambda _text: 10,
    )


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """A single user message, enough to drive one turn."""
    return [
        UIMessage(
            id="msg-1",
            role="user",
            content="Hello",
            parts=[TextUIPart(type="text", text="Hello")],
        )
    ]


async def _collect(service, ui_messages):
    """Drain the service's stream into a list of frames."""
    chunks = []
    async for chunk in service.stream_data_async(ui_messages):
        chunks.append(chunk)
    return chunks


@pytest.mark.asyncio
async def test_stop_persists_the_partial_assistant_message(ui_messages):
    """The poison pill stores the user message and the text produced so far."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, then arm the stop before the next one."""
        yield "Partial "
        service.stop_streaming()
        # The stop check is throttled to once every 2s; reset the clock so the
        # next event checks the cache instead of skipping it.
        service._last_stop_check = 0
        yield "answer"
        yield " never streamed"

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        with pytest.raises(StreamCancelException):
            await _collect(service, ui_messages)

    await sync_to_async(conversation.refresh_from_db)()
    # "answer" is the delta that arrived with the stop: Pydantic AI applies a
    # delta before emitting its event, and the stop is checked after, so the
    # persisted text runs one delta past what the browser rendered.
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Partial answer"),
    ]


@pytest.mark.asyncio
async def test_disconnect_persists_the_partial_assistant_message(ui_messages):
    """A cancelled consumer (client disconnect) stores the text streamed so far."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, then block where the cancellation will land."""
        yield "Partial answer "
        streaming.set()
        await asyncio.sleep(60)
        yield "never streamed"

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        task = asyncio.create_task(_collect(service, ui_messages))
        await streaming.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Partial answer "),
    ]


@pytest.mark.asyncio
async def test_interrupted_message_keeps_the_streamed_id(ui_messages):
    """The stored message carries the id announced in the stream's start frame."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()
    chunks = []

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, then block where the cancellation will land."""
        yield "Partial answer "
        streaming.set()
        await asyncio.sleep(60)

    async def _consume():
        """Keep every frame so the start frame's message id can be read back."""
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        task = asyncio.create_task(_consume())
        await streaming.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    start_frame = json.loads(stream_frames(chunks)[0])
    assert start_frame["type"] == "start"

    await sync_to_async(conversation.refresh_from_db)()
    assert conversation.messages[-1].id == start_frame["messageId"]


@pytest.mark.asyncio
async def test_interruption_before_any_text_keeps_the_user_message(ui_messages):
    """Nothing was produced, but the user's own message is still stored."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Block before producing anything at all."""
        streaming.set()
        await asyncio.sleep(60)
        yield "never streamed"

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        task = asyncio.create_task(_collect(service, ui_messages))
        await streaming.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello")
    ]


@pytest.mark.asyncio
async def test_interrupted_turn_counts_towards_usage(ui_messages):
    """The interrupted turn's tokens land in the conversation's usage totals."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, then block where the cancellation will land."""
        yield "Partial answer "
        streaming.set()
        await asyncio.sleep(60)

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        task = asyncio.create_task(_collect(service, ui_messages))
        await streaming.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await sync_to_async(conversation.refresh_from_db)()
    assert conversation.agent_usage["promptTokens"] > 0
    assert conversation.agent_usage["completionTokens"] > 0


@pytest.mark.asyncio
async def test_a_following_turn_runs_on_the_interrupted_history(ui_messages):
    """The interrupted turn loads back into the next run and the next turn completes."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()

    async def _interrupted_stream(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, then block where the cancellation will land."""
        yield "Partial answer "
        streaming.set()
        await asyncio.sleep(60)

    interrupted_model = FunctionModel(stream_function=_interrupted_stream)
    with service.conversation_agent.override(model=interrupted_model):
        task = asyncio.create_task(_collect(service, ui_messages))
        await streaming.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await sync_to_async(conversation.refresh_from_db)()

    async def _complete_stream(_messages: list[ModelMessage], _info: AgentInfo):
        """Answer the follow-up in full."""
        yield "Continued."

    follow_up = [
        UIMessage(
            id="msg-2",
            role="user",
            content="Continue",
            parts=[TextUIPart(type="text", text="Continue")],
        )
    ]
    owner = await sync_to_async(getattr)(conversation, "owner")
    next_service = AIAgentService(conversation, user=owner)
    complete_model = FunctionModel(stream_function=_complete_stream)
    with next_service.conversation_agent.override(model=complete_model):
        await _collect(next_service, follow_up)

    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Partial answer "),
        ("user", "Continue"),
        ("assistant", "Continued."),
    ]


@pytest.mark.asyncio
async def test_interruption_during_a_tool_call_leaves_the_conversation_usable(ui_messages):
    """A turn cut off mid tool-call does not block the following turn."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()

    async def _interrupted_stream(_messages: list[ModelMessage], _info: AgentInfo):
        """Start streaming a tool call, then block before it is complete."""
        yield {0: DeltaToolCall(name="web_search", json_args='{"query":')}
        streaming.set()
        await asyncio.sleep(60)
        yield {0: DeltaToolCall(json_args=' "weather"}')}

    interrupted_model = FunctionModel(stream_function=_interrupted_stream)
    with service.conversation_agent.override(model=interrupted_model):
        task = asyncio.create_task(_collect(service, ui_messages))
        await streaming.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await sync_to_async(conversation.refresh_from_db)()
    assert [message.role for message in conversation.messages] == ["user", "assistant"]

    async def _complete_stream(_messages: list[ModelMessage], _info: AgentInfo):
        """Answer the follow-up in full."""
        yield "Back to normal."

    follow_up = [
        UIMessage(
            id="msg-2",
            role="user",
            content="Never mind",
            parts=[TextUIPart(type="text", text="Never mind")],
        )
    ]
    owner = await sync_to_async(getattr)(conversation, "owner")
    next_service = AIAgentService(conversation, user=owner)
    complete_model = FunctionModel(stream_function=_complete_stream)
    with next_service.conversation_agent.override(model=complete_model):
        await _collect(next_service, follow_up)

    await sync_to_async(conversation.refresh_from_db)()
    assert conversation.messages[-1].role == "assistant"
    assert conversation.messages[-1].content == "Back to normal."


@pytest.mark.asyncio
async def test_a_completed_stream_still_persists_normally(ui_messages):
    """Regression guard: the uninterrupted path is untouched."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Answer in full."""
        yield "Full answer."

    with service.conversation_agent.override(model=FunctionModel(stream_function=_stream_function)):
        await _collect(service, ui_messages)

    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Full answer."),
    ]
    assert not (conversation.messages[-1].metadata or {}).get("interrupted")
