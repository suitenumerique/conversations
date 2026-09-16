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

from core.models import ChatCooldownSettings

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.models import ChatConversation
from chat.rate_limiting import get_tokens_last_window
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
    chunks = []

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, then arm the stop before the next one."""
        yield "Partial "
        service.stop_streaming()
        # The stop check is throttled to once every 2s; reset the clock so the
        # next event checks the cache instead of skipping it.
        service._last_stop_check = 0
        yield "answer"
        yield " never streamed"

    async def _consume():
        """Keep every frame so the streamed text can be compared to what was saved."""
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        await _consume()

    await sync_to_async(conversation.refresh_from_db)()
    # "answer" is the delta that arrived with the stop: Pydantic AI applies a
    # delta before emitting its event, and the stop is checked after, so the
    # persisted text runs one delta past what the browser rendered.
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Partial answer"),
    ]
    # A stop closes the stream like a normal end - the terminator is there, so
    # the browser sees a finished response rather than a severed connection.
    assert stream_frames(chunks)[-1] == "[DONE]"
    streamed_text = "".join(
        event["delta"]
        for frame in stream_frames(chunks)
        if frame != "[DONE]"
        for event in [json.loads(frame)]
        if event["type"] == "text-delta"
    )
    assert streamed_text == "Partial "


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
    """Nothing was produced, but the user's own message is still stored.

    A following turn must still see and append its own user bubble: the
    trailing message after this interruption is "user", the same stale state
    a role-based guard would mistake for "already persisted this turn".
    """
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
        ("user", "Continue"),
        ("assistant", "Continued."),
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
async def test_interrupted_turn_is_recorded_for_rate_limiting(ui_messages):
    """An interrupted turn still spends against the user's cooldown window."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    streaming = asyncio.Event()
    window_seconds = await sync_to_async(lambda: ChatCooldownSettings.get_solo().window_seconds)()

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
    tokens_in_window = await sync_to_async(get_tokens_last_window)(service.user.pk, window_seconds)
    request_tokens = (
        conversation.agent_usage["promptTokens"] + conversation.agent_usage["completionTokens"]
    )
    assert tokens_in_window == request_tokens


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


@pytest.mark.asyncio
async def test_stop_is_honoured_while_the_run_is_blocked(ui_messages):
    """The stop pill lands even when the run emits no further events.

    `_process_agent_nodes` only reads the pill between two streamed events, so
    a run parked in a tool call or a provider retry used to ignore Stop until
    it unblocked - minutes later, with the browser already gone. The watcher
    cancels the run where it is blocked instead.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one chunk, arm the stop, then block with nothing to emit."""
        yield "Partial answer"
        service.stop_streaming()
        await asyncio.sleep(60)
        yield "never streamed"

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        # Bounded so a regression fails the test instead of hanging it.
        chunks = await asyncio.wait_for(_collect(service, ui_messages), timeout=10)

    assert stream_frames(chunks)[-1] == "[DONE]"
    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "Partial answer"),
    ]


@pytest.mark.asyncio
async def test_turn_is_saved_before_the_title_is_generated(ui_messages, settings):
    """Title generation is an LLM round-trip; the turn must already be on disk.

    Saving after it left a multi-second window where a page reload showed an
    empty conversation.
    """
    settings.AUTO_TITLE_AFTER_USER_MESSAGES = 1
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    stored_when_title_ran = []

    def _read_stored_messages():
        """Read the conversation's messages straight from the database."""
        return ChatConversation.objects.get(pk=conversation.pk).messages

    async def _generate_title():
        """Record what was already persisted by the time the title is built."""
        stored_when_title_ran.extend(await sync_to_async(_read_stored_messages)())
        return "A title"

    service._generate_title = _generate_title

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream a complete answer."""
        yield "Complete answer"

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        await _collect(service, ui_messages)

    assert [(message.role, message.content) for message in stored_when_title_ran] == [
        ("user", "Hello"),
        ("assistant", "Complete answer"),
    ]
    await sync_to_async(conversation.refresh_from_db)()
    assert conversation.title == "A title"


@pytest.mark.asyncio
async def test_interruption_while_a_tool_runs_leaves_the_conversation_usable(ui_messages):
    """A turn cut off while a tool executes does not brick the conversation.

    Distinct from the mid-stream case above: here the model finished streaming
    its tool call before the cancellation landed, so Pydantic AI does not stamp
    the response `interrupted` - it only does that for a response cut off while
    streaming. A history whose last response holds tool calls that will never
    get returns is refused on the next turn, and the refusal is permanent:
    every later turn reads the same history back.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    running = asyncio.Event()

    @service.conversation_agent.tool_plain
    async def slow_lookup() -> str:
        """Block where the cancellation lands, once the call is fully streamed."""
        running.set()
        await asyncio.sleep(60)
        return "never returned"

    async def _interrupted_stream(_messages: list[ModelMessage], _info: AgentInfo):
        """Stream one complete tool call and let the graph run it."""
        yield {0: DeltaToolCall(name="slow_lookup", json_args="{}")}

    interrupted_model = FunctionModel(stream_function=_interrupted_stream)
    with service.conversation_agent.override(model=interrupted_model):
        task = asyncio.create_task(_collect(service, ui_messages))
        await running.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

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
    await sync_to_async(conversation.refresh_from_db)()
    owner = await sync_to_async(getattr)(conversation, "owner")
    next_service = AIAgentService(conversation, user=owner)
    complete_model = FunctionModel(stream_function=_complete_stream)
    with next_service.conversation_agent.override(model=complete_model):
        await _collect(next_service, follow_up)

    await sync_to_async(conversation.refresh_from_db)()
    assert conversation.messages[-1].role == "assistant"
    assert conversation.messages[-1].content == "Back to normal."


@pytest.mark.asyncio
async def test_finished_turn_survives_a_disconnect_while_frames_are_draining(ui_messages):
    """A run that completed is stored even if the client leaves before the last frame.

    The node stream is consumed by a producer task, so the run can finish
    while the consumer still has queued frames to write to the socket. A
    disconnect during that drain never reaches `_finalize_conversation`, and
    the turn - a complete one, fully generated and paid for - used to be lost
    outright.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    parked = asyncio.Event()
    release = asyncio.Event()
    persisted = asyncio.Event()
    chunks = []

    persist_completed_turn = service._persist_completed_turn

    async def _signal_when_persisted(*args, **kwargs):
        """Run the real write, then let the test know it landed."""
        await persist_completed_turn(*args, **kwargs)
        persisted.set()

    service._persist_completed_turn = _signal_when_persisted

    async def _stream_function(_messages: list[ModelMessage], _info: AgentInfo):
        """Answer in full; the run ends as soon as this returns."""
        yield "A complete answer"

    async def _stalled_consume():
        """Read two frames, then stop reading like a client that went away."""
        async for chunk in service.stream_data_async(ui_messages):
            chunks.append(chunk)
            if len(chunks) >= 2:
                parked.set()
                await release.wait()

    model = FunctionModel(stream_function=_stream_function)
    with service.conversation_agent.override(model=model):
        task = asyncio.create_task(_stalled_consume())
        await parked.wait()
        # Wait for the producer to finish the turn and store it while the
        # consumer is stalled on the socket - the window this test is about.
        # Bounded so a regression fails the test instead of hanging it, and
        # signalled rather than slept so a slow worker cannot cancel first and
        # quietly send the run down the interrupted path instead.
        await asyncio.wait_for(persisted.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.content) for message in conversation.messages] == [
        ("user", "Hello"),
        ("assistant", "A complete answer"),
    ]
    # The run finished: this is a stored complete turn, not a salvaged partial one.
    assert not (conversation.messages[-1].metadata or {}).get("interrupted")
