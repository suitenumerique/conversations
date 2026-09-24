"""What a turn leaves behind when it never reaches the end of the run.

Generation is driven by the HTTP response, so a disconnect or a stop closes the
generator where it stands and `_finalize_conversation` never runs. These tests
cover the two writes that happen before it: the question, stored before the
model is called, and the answer streamed so far, checkpointed as it comes.
"""

# pylint: disable=protected-access  # tests intentionally access private members
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)

QUESTION = UIMessage(
    id="q-1",
    role="user",
    content="Say hello",
    parts=[TextUIPart(type="text", text="Say hello")],
)


async def _hello_model(_messages: list[ModelMessage], _info: AgentInfo):
    """Stream an answer in two parts, so a reader can stop after the first."""
    yield "Hello"
    yield " there"


def _service_with_model(conversation, stream_function):
    """Build the service against a scripted model, as the view fixture does."""
    service = AIAgentService(conversation, user=conversation.owner)
    service.conversation_agent._model = FunctionModel(stream_function=stream_function)
    return service


@pytest.mark.asyncio
async def test_the_question_is_stored_before_the_model_answers():
    """The question is on the conversation while the model is still running."""
    conversation = await sync_to_async(ChatConversationFactory)()
    seen = []

    async def model_reading_the_conversation(_messages, _info):
        """Read back the conversation from the database mid-run."""
        stored = await sync_to_async(
            lambda: list(type(conversation).objects.get(pk=conversation.pk).messages)
        )()
        seen.append([(message.role, message.id) for message in stored])
        yield "Hello"

    service = _service_with_model(conversation, model_reading_the_conversation)
    async for _ in service.stream_data_async([QUESTION]):
        pass

    assert seen == [[("user", "q-1")]]


@pytest.mark.asyncio
async def test_an_interrupted_stream_keeps_the_answer_streamed_so_far():
    """Closing the stream mid-answer leaves the question and the partial answer."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)

    with patch("chat.clients.pydantic_ai.STREAM_CHECKPOINT_INTERVAL_SECONDS", 0):
        stream = service.stream_data_async([QUESTION])
        async for chunk in stream:
            if '"delta":"Hello"' in chunk:
                break

    # Read the conversation at the point the reader walks away. Nothing runs
    # after this in a real interruption - the generator is closed where it
    # stands and the end-of-run write never happens - so this is the state the
    # turn is left in.
    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.id) for message in conversation.messages] == [
        ("user", "q-1"),
        ("assistant", service._model_response_message_id),
    ]
    partial = conversation.messages[1]
    assert partial.metadata == {"interrupted": True}
    assert [part.text for part in partial.parts] == ["Hello"]
    # The turn is in the model history too, so a later one carries on from it.
    assert [message["kind"] for message in conversation.pydantic_messages] == [
        "request",
        "response",
    ]
    assert conversation.pydantic_messages[-1]["parts"][-1]["content"] == "Hello"


@pytest.mark.asyncio
async def test_a_completed_turn_replaces_its_checkpoint():
    """The checkpoint written during the run is gone once the turn completes."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)

    with (
        patch("chat.clients.pydantic_ai.STREAM_CHECKPOINT_INTERVAL_SECONDS", 0),
        patch.object(
            AIAgentService,
            "_apply_turn",
            autospec=True,
            side_effect=AIAgentService._apply_turn,
        ) as write,
    ):
        async for _ in service.stream_data_async([QUESTION]):
            pass

    # Checkpoints, then the finished turn: each write lands over the last.
    assert write.call_count > 1, "the answer was never checkpointed"

    await sync_to_async(conversation.refresh_from_db)()
    assert [message.role for message in conversation.messages] == ["user", "assistant"]
    answer = conversation.messages[1]
    assert (answer.metadata or {}).get("interrupted") is None
    assert [part.text for part in answer.parts] == ["Hello there"]
    # The checkpoints left nothing behind in the history either.
    assert [message["kind"] for message in conversation.pydantic_messages] == [
        "request",
        "response",
    ]


@pytest.mark.asyncio
async def test_stopping_keeps_the_answer_streamed_so_far():
    """The stop button ends the stream cleanly and keeps the partial answer."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = None

    async def stopped_model(_messages, _info):
        """Answer, then press stop between two chunks."""
        yield "Hello"
        service.stop_streaming()
        # The in-band check is throttled; this is the throttle's own clock,
        # reset so the next check reads the pill instead of skipping it.
        service._last_stop_check = 0
        yield " there"

    service = _service_with_model(conversation, stopped_model)
    chunks = [chunk async for chunk in service.stream_data_async([QUESTION])]

    # Terminated like any other stream: before this was caught, the exception
    # escaped through the response iterator under ASGI.
    assert chunks[-1] == "data: [DONE]\n\n"

    await sync_to_async(conversation.refresh_from_db)()
    assert [message.role for message in conversation.messages] == ["user", "assistant"]
    answer = conversation.messages[1]
    assert answer.metadata == {"interrupted": True}
    # What the model had produced when the stop landed, which is at least the
    # chunk before it. Where exactly the cut falls is the provider's business.
    assert answer.parts[0].text.startswith("Hello")


@pytest.mark.asyncio
async def test_a_checkpoint_carries_the_turn_structure_not_just_its_text(settings):
    """A tool call is part of what the turn produced, so it is stored as one."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]
    conversation = await sync_to_async(ChatConversationFactory)()
    calls = []

    async def model_calling_a_tool(messages: list[ModelMessage], info: AgentInfo):
        """Call the weather tool, then answer from its result."""
        calls.append(len(messages))
        if len(calls) == 1:
            yield {
                0: DeltaToolCall(
                    name=info.function_tools[0].name,
                    json_args='{"location": "Paris", "unit": "celsius"}',
                    tool_call_id="call-1",
                )
            }
            return
        yield "It is mild."

    service = _service_with_model(conversation, model_calling_a_tool)

    # The tool call resolving is a forced checkpoint, so the turn is on disk
    # before the answer that follows it.
    stored = []
    original = AIAgentService._apply_turn

    def recording_apply(self, **kwargs):
        """Record what each write of the turn puts on the conversation."""
        result = original(self, **kwargs)
        stored.append(
            [
                [getattr(part, "type", None) for part in message.parts]
                for message in self.conversation.messages
            ]
        )
        return result

    with (
        patch("chat.clients.pydantic_ai.STREAM_CHECKPOINT_INTERVAL_SECONDS", 0),
        patch.object(AIAgentService, "_apply_turn", recording_apply),
    ):
        async for _ in service.stream_data_async([QUESTION]):
            pass

    # Some write of the turn held the tool call, which a text-only checkpoint
    # would have dropped on the floor.
    assert any(
        any(part == "tool-get_current_weather" for parts in write for part in parts)
        for write in stored
    ), stored

    await sync_to_async(conversation.refresh_from_db)()
    answer = conversation.messages[-1]
    assert [part.type for part in answer.parts] == ["tool-get_current_weather", "text"]
    # A checkpoint stamps a dangling tool call as interrupted so the history
    # stays replayable. That stamp belongs to the copy it persists: the turn
    # went on to finish, and the history has to say so.
    assert [
        message["state"]
        for message in conversation.pydantic_messages
        if message["kind"] == "response"
    ] == ["complete", "complete"]


@pytest.mark.asyncio
async def test_a_retried_question_replaces_the_unanswered_one():
    """A trailing question was never answered, so the retry takes its place."""
    conversation = await sync_to_async(ChatConversationFactory)(messages=[QUESTION])
    service = AIAgentService(conversation, user=conversation.owner)

    retry = UIMessage(
        id="q-2",
        role="user",
        content="Say hello",
        parts=[TextUIPart(type="text", text="Say hello")],
    )
    await service._persist_user_message(retry)

    await sync_to_async(conversation.refresh_from_db)()
    assert [(message.role, message.id) for message in conversation.messages] == [("user", "q-2")]
