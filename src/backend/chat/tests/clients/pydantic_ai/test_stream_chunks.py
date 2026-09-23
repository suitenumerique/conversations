"""What a turn leaves behind in `ChatStreamChunk`, and what is made of it.

A turn appends what it produces as it produces it, so an interruption cannot
take it back. Nothing is written when the interruption happens: by then the
turn is in no position to write anything, which is the whole point.
"""

# pylint: disable=protected-access
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from chat import stream_chunks
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.constants import STREAM_LIVE_WINDOW_SECONDS
from chat.factories import ChatConversationFactory
from chat.models import ChatStreamChunk

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


def _service_with_model(conversation, stream_function, owner=None):
    """Build the service against a scripted model, as the view fixture does."""
    service = AIAgentService(conversation, user=owner or conversation.owner)
    service.conversation_agent._model = FunctionModel(stream_function=stream_function)
    return service


async def _chunks(conversation):
    """The conversation's chunks, oldest first."""
    return await sync_to_async(lambda: list(conversation.stream_chunks.all()))()


@pytest.mark.asyncio
async def test_an_interrupted_turn_is_readable_from_its_chunks():
    """Walking away mid-answer leaves the question and what was answered."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)

    stream = service.stream_data_async([QUESTION])
    async for chunk in stream:
        if '"delta":"Hello"' in chunk:
            break

    # Read at the point the reader walks away. Nothing runs after this in a
    # real interruption, so this is the state the turn is left in.
    chunks = await _chunks(conversation)
    assert chunks, "the turn wrote nothing"

    messages = stream_chunks.interrupted_messages(chunks)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].parts[0].text == "Say hello"
    assert messages[1].parts[0].text.startswith("Hello")
    assert messages[1].metadata == {"interrupted": True}
    assert messages[1].id == service._model_response_message_id

    # Still untouched: the chunks are the copy of record until a turn lands or
    # the next one folds them.
    await sync_to_async(conversation.refresh_from_db)()
    assert conversation.messages == []
    assert conversation.pydantic_messages == []


@pytest.mark.asyncio
async def test_the_question_is_written_before_the_model_answers():
    """Everything slow happens before the first token: preparing the run,
    parsing an attached document, waiting on a summary. A turn cut short in
    that window has to leave the question behind at least."""
    conversation = await sync_to_async(ChatConversationFactory)()
    seen = []

    async def model_reading_the_chunks(_messages, _info):
        """Read the chunks back from the database before answering."""
        seen.extend(stream_chunks.interrupted_messages(await _chunks(conversation)))
        yield "Hello"

    service = _service_with_model(conversation, model_reading_the_chunks)
    async for _ in service.stream_data_async([QUESTION]):
        pass

    assert [message.role for message in seen] == ["user"]
    assert seen[0].parts[0].text == "Say hello"


@pytest.mark.asyncio
async def test_a_turn_that_lands_leaves_no_chunks():
    """The chunks are scaffolding: the finished turn replaces them."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)

    with patch("chat.clients.pydantic_ai.STREAM_TEXT_FLUSH_INTERVAL_SECONDS", 0):
        async for _ in service.stream_data_async([QUESTION]):
            pass

    assert await _chunks(conversation) == []
    await sync_to_async(conversation.refresh_from_db)()
    assert [message.role for message in conversation.messages] == ["user", "assistant"]
    answer = conversation.messages[1]
    assert (answer.metadata or {}).get("interrupted") is None
    assert answer.parts[0].text == "Hello there"


@pytest.mark.asyncio
async def test_text_is_appended_rather_than_rewritten():
    """Each row carries only what is new, which is what keeps them cheap."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)
    written = []

    original = ChatStreamChunk.objects.acreate

    async def recording_create(**kwargs):
        """Record every row the turn appends."""
        written.append(
            {
                "seq": kwargs["seq"],
                "text": kwargs["text"],
                "parts": kwargs["parts"],
                "snapshot": bool(kwargs["parts"]),
            }
        )
        return await original(**kwargs)

    with (
        patch("chat.clients.pydantic_ai.STREAM_TEXT_FLUSH_INTERVAL_SECONDS", 0),
        patch.object(ChatStreamChunk.objects, "acreate", recording_create),
    ):
        async for _ in service.stream_data_async([QUESTION]):
            pass

    # The turn's first output earns a snapshot, so there is a request for the
    # answer to belong to; everything after it is only what was added.
    assert written[0]["snapshot"] is True

    # Whatever the split between the snapshot and the text rows, reading them
    # back must give the answer once, not twice.
    folded = stream_chunks.fold(
        [ChatStreamChunk(seq=row["seq"], text=row["text"], parts=row["parts"]) for row in written]
    )
    assert folded[-1].parts[-1].content == "Hello there"


@pytest.mark.asyncio
async def test_stopping_closes_the_stream_and_keeps_what_was_produced():
    """Stop ends the stream like any other, and the chunks stand as the answer."""
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
    chunks_out = [chunk async for chunk in service.stream_data_async([QUESTION])]

    # Before this was caught, the exception escaped through the response
    # iterator under ASGI instead of ending the stream.
    assert chunks_out[-1] == "data: [DONE]\n\n"

    messages = stream_chunks.interrupted_messages(await _chunks(conversation))
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].metadata == {"interrupted": True}


@pytest.mark.asyncio
async def test_an_interrupted_turn_still_pays_its_cooldown():
    """The tokens were spent whether or not the turn reached the end."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)
    charged = []

    with patch.object(
        AIAgentService,
        "_record_tokens",
        autospec=True,
        side_effect=lambda self, total: charged.append(total) or 0,
    ):
        stream = service.stream_data_async([QUESTION])
        async for chunk in stream:
            if '"delta":"Hello"' in chunk:
                break

    # Charged while streaming, so walking away here does not get the turn for
    # free; the window adds up, so the increments total what one final call
    # would have charged.
    assert charged, "nothing was charged before the turn ended"


@pytest.mark.asyncio
async def test_the_next_turn_folds_what_the_last_one_left():
    """An interrupted turn joins the history rather than haunting the chunks."""
    conversation = await sync_to_async(ChatConversationFactory)()
    interrupted = _service_with_model(conversation, _hello_model)

    stream = interrupted.stream_data_async([QUESTION])
    async for chunk in stream:
        if '"delta":"Hello"' in chunk:
            break
    assert await _chunks(conversation) != []

    # Age the trail past the window in which it could still be a turn that is
    # simply slow: only then does the next turn take it as abandoned.
    await sync_to_async(
        lambda: ChatStreamChunk.objects.filter(conversation=conversation).update(
            created_at=timezone.now() - timedelta(seconds=STREAM_LIVE_WINDOW_SECONDS + 5)
        )
    )()

    # A second turn on the same conversation. The owner is carried over
    # explicitly: reading it again after a refresh would hit the database from
    # async context.
    owner = interrupted.user
    await sync_to_async(conversation.refresh_from_db)()
    second = _service_with_model(conversation, _hello_model, owner=owner)
    async for _ in second.stream_data_async([QUESTION]):
        pass

    await sync_to_async(conversation.refresh_from_db)()
    assert [message.role for message in conversation.messages] == [
        "user",
        "assistant",  # the interrupted turn, folded in
        "user",
        "assistant",  # the one that landed
    ]
    assert conversation.messages[1].metadata == {"interrupted": True}
    # The model replays it too, so it can carry on from where it was cut.
    assert [message["kind"] for message in conversation.pydantic_messages] == [
        "request",
        "response",
        "request",
        "response",
    ]


@pytest.mark.asyncio
async def test_two_turns_at_once_do_not_corrupt_each_other():
    """Two tabs on one conversation: each turn owns its own trail.

    Everything used to be scoped to the conversation, so the second turn folded
    the first one's rows while it was still writing them, deleted them, and the
    two then collided on `seq`.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    owner = await sync_to_async(lambda: conversation.owner)()

    # The first turn is left mid-answer, its trail still being written to.
    first = _service_with_model(conversation, _hello_model, owner=owner)
    stream = first.stream_data_async([QUESTION])
    async for chunk in stream:
        if '"delta":"Hello"' in chunk:
            break
    abandoned = await _chunks(conversation)
    assert abandoned

    # A second turn starts on the same conversation while the first is live.
    second = _service_with_model(conversation, _hello_model, owner=owner)
    async for _ in second.stream_data_async([QUESTION]):
        pass

    await sync_to_async(conversation.refresh_from_db)()
    # The second turn landed on its own, and took only its own rows with it.
    assert [message.role for message in conversation.messages] == ["user", "assistant"]
    assert (conversation.messages[-1].metadata or {}).get("interrupted") is None

    # The first turn's trail is untouched: not folded as interrupted while it
    # was still running, and not deleted by the turn that finished.
    remaining = await _chunks(conversation)
    assert {chunk.run_id for chunk in remaining} == {abandoned[0].run_id}


@pytest.mark.asyncio
async def test_a_snapshot_carries_structure_a_text_row_cannot(settings):
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
    seen = []

    stream = service.stream_data_async([QUESTION])
    async for chunk in stream:
        if "tool-output-available" in chunk:
            seen = stream_chunks.interrupted_messages(await _chunks(conversation))
            break

    assert seen, "nothing was stored by the time the tool had answered"
    assert any(
        part.type == "tool-get_current_weather" for message in seen for part in message.parts
    ), [part.type for message in seen for part in message.parts]


@pytest.mark.asyncio
async def test_a_turn_is_live_while_its_chunks_keep_coming():
    """Freshness is what tells an answer on its way from one cut short."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)

    stream = service.stream_data_async([QUESTION])
    async for chunk in stream:
        if '"delta":"Hello"' in chunk:
            break

    assert stream_chunks.is_live(await _chunks(conversation)) is True
    assert stream_chunks.is_live([]) is False
