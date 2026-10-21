"""How a turn that calls tools reads back from, and is filed from, its chunks."""

import uuid

import pytest

from chat import stream_chunks
from chat.factories import ChatConversationFactory
from chat.models import ChatConversation, ChatStreamChunk

pytestmark = pytest.mark.django_db


TOOL_ROUNDS_SNAPSHOT = [
    {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "Search"}]},
    {
        "kind": "response",
        "parts": [{"part_kind": "tool-call", "tool_name": "web_search", "args": {}}],
    },
    {
        "kind": "request",
        "parts": [{"part_kind": "tool-return", "tool_name": "web_search", "content": "r1"}],
    },
    {
        "kind": "response",
        "parts": [{"part_kind": "tool-call", "tool_name": "web_search", "args": {}}],
    },
    {
        "kind": "request",
        "parts": [{"part_kind": "tool-return", "tool_name": "web_search", "content": "r2"}],
    },
    {"kind": "response", "parts": [{"part_kind": "text", "content": "Found"}]},
]


def test_a_turn_with_tool_calls_reads_as_one_answer():
    """Each tool round is its own model response, but the reader sees one
    answer, as it does once the turn lands: one bubble per round put a row of
    empty copy buttons on screen while the model kept working."""
    trail = [
        ChatStreamChunk(run_id=uuid.uuid4(), message_id="a-1", seq=0, parts=TOOL_ROUNDS_SNAPSHOT),
    ]

    messages = stream_chunks.interrupted_messages(trail)

    assert [m.role for m in messages] == ["user", "assistant"]
    assert [part.type for part in messages[1].parts] == [
        "tool-web_search",
        "tool-web_search",
        "text",
    ]
    assert messages[1].id == "a-1"
    # The model history keeps every round: only the reader sees them merged.
    assert len(stream_chunks.fold(trail)) == 6


def test_a_folded_turn_with_tool_calls_is_stored_as_one_answer():
    """Filing the trail stores what the reader saw: one question, one answer,
    while the model history keeps every round."""
    conversation = ChatConversationFactory()
    run_id = uuid.uuid4()
    ChatStreamChunk.objects.create(
        conversation=conversation,
        run_id=run_id,
        message_id="a-1",
        seq=0,
        parts=TOOL_ROUNDS_SNAPSHOT,
    )

    assert stream_chunks.close(conversation, run_id) is True

    stored = ChatConversation.objects.get(pk=conversation.pk)
    assert [message.role for message in stored.messages] == ["user", "assistant"]
    assert stored.messages[1].id == "a-1"
    assert len(stored.pydantic_messages) == 6
