"""What `TurnTrail` writes to `ChatStreamChunk` while a turn runs."""

# pylint: disable=protected-access
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from chat import stream_chunks
from chat.factories import ChatConversationFactory
from chat.models import ChatStreamChunk
from chat.turn.trail import TurnTrail

pytestmark = pytest.mark.django_db(transaction=True)


async def _chunks(conversation):
    """The conversation's chunks, oldest first."""
    return await sync_to_async(lambda: list(conversation.stream_chunks.all()))()


def _ignore_log(*_args) -> None:
    """Stand-in for the service's turn log, which these tests do not read."""


@pytest.mark.asyncio
async def test_a_blocked_turn_says_it_is_still_running():
    """A turn produces nothing for minutes while a document is parsed or a tool
    runs. The keepalive loop is the only thing ticking then, so the beat it
    appends is what keeps the trail from reading as abandoned."""
    conversation = await sync_to_async(ChatConversationFactory)()
    turn = TurnTrail(conversation, log=_ignore_log)
    turn.message_id = "m-1"

    await turn.beat()
    await turn.beat()

    trail = await _chunks(conversation)
    assert [(chunk.text, chunk.parts) for chunk in trail] == [("", None), ("", None)]
    # Heartbeats alone hold no turn: nothing to fold, nothing to wait for.
    assert stream_chunks.fold(trail) == []
    assert stream_chunks.is_live(trail) is False

    # A turn that is really working stored its question before anything slow.
    await turn.append_question("Say hello", [])
    await turn.beat()

    trail = await _chunks(conversation)
    assert stream_chunks.is_live(trail) is True


@pytest.mark.asyncio
async def test_a_snapshot_drops_the_rows_it_supersedes():
    """A snapshot holds the whole turn, so the rows before it are unreachable.

    `fold` resets its text on every snapshot it meets, so keeping them grows
    the trail with the square of the steps for rows no reader can reach.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    turn = TurnTrail(conversation, log=_ignore_log)
    turn.message_id = "m-1"

    with patch("chat.turn.trail.STREAM_TEXT_FLUSH_INTERVAL_SECONDS", 0):
        await turn.append_question("Say hello", [])
        await turn.beat()
        await turn.append_text("Hello")
        assert len(await _chunks(conversation)) == 3

        await turn._write_snapshot(
            [
                ModelRequest(parts=[UserPromptPart(content=["Say hello"])], kind="request"),
                ModelResponse(parts=[TextPart(content="Hello")], kind="response"),
            ]
        )

    trail = await _chunks(conversation)
    assert [(chunk.seq, chunk.parts is not None) for chunk in trail] == [(3, True)]
    folded = stream_chunks.fold(trail)
    assert folded[-1].parts[-1].content == "Hello"


@pytest.mark.asyncio
async def test_a_superseding_snapshot_still_says_the_question_is_stored():
    """The flag that stops the question being shown twice lives on a row that a
    later snapshot deletes, so every snapshot has to carry it."""
    conversation = await sync_to_async(ChatConversationFactory)()
    turn = TurnTrail(conversation, log=_ignore_log)
    turn.message_id = "m-1"
    turn.question_stored = True

    await turn.append_question("Say hello", [])
    await turn._write_snapshot(
        [
            ModelRequest(parts=[UserPromptPart(content=["Say hello"])], kind="request"),
            ModelResponse(parts=[TextPart(content="Hello")], kind="response"),
        ]
    )

    trail = await _chunks(conversation)
    assert [chunk.question_in_messages for chunk in trail] == [True]
    # Only the answer: the question is already in `messages`.
    shown = stream_chunks.interrupted_messages(trail)
    assert [message.role for message in shown] == ["assistant"]


@pytest.mark.asyncio
async def test_a_beat_takes_back_its_row_if_the_turn_landed_meanwhile():
    """The flag check and the insert are not one step.

    A turn landing in between deletes its trail, and a beat row written after
    that would keep the conversation reading as still generating for the whole
    liveness window.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    turn = TurnTrail(conversation, log=_ignore_log)

    original = TurnTrail._write_chunk

    async def land_while_writing(self, **kwargs):
        """Write the row, then have the turn land before the beat looks again."""
        seq = await original(self, **kwargs)
        self.landed = True
        return seq

    with patch.object(TurnTrail, "_write_chunk", land_while_writing):
        await turn.beat()

    assert await _chunks(conversation) == []


def test_the_sync_beat_takes_back_its_row_too():
    """The WSGI path has the same gap, between two threads rather than tasks."""
    conversation = ChatConversationFactory()
    turn = TurnTrail(conversation, log=_ignore_log)

    original = ChatStreamChunk.objects.create

    def land_while_writing(**kwargs):
        """Write the row, then have the turn land before the beat looks again."""
        chunk = original(**kwargs)
        turn.landed = True
        return chunk

    with patch.object(ChatStreamChunk.objects, "create", land_while_writing):
        turn.beat_sync()

    assert not conversation.stream_chunks.exists()
