"""The turn trace (`chat.turn`) carries the ids needed to follow one turn in the logs."""

from django.test import AsyncClient, Client

import pytest
from asgiref.sync import sync_to_async

from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)

# Ids bound for a chat turn, which a later request must not inherit.
TURN_IDS = ("conversation_id", "message_id")


def _assert_turn_lines_carry_ids(json_logs, conversation):
    """Every turn line names the request and conversation, and from the stream on, the answer."""
    turn_lines = [line for line in json_logs() if line["logger"] == "chat.turn"]
    events = [line["event"] for line in turn_lines]
    assert events[0] == "turn_requested"
    assert "turn_stored" in events
    request_id = turn_lines[0]["request_id"]
    [started] = [line for line in json_logs() if line["event"] == "request_started"]
    assert started["request_id"] == request_id
    for line in turn_lines:
        assert line["conversation_id"] == str(conversation.pk)
        assert line["request_id"] == request_id
    answer_lines = turn_lines[events.index("stream_opened") :]
    message_id = answer_lines[0]["message_id"]
    assert message_id
    assert [line["message_id"] for line in answer_lines] == [message_id] * len(answer_lines)


def test_turn_lines_carry_ids_sync(
    api_client, mock_openai_stream, hello_conversation_data, json_logs
):
    """Sync server mode (WSGI)."""
    conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_login(conversation.owner)

    response = api_client.post(
        f"/api/v1.0/chats/{conversation.pk}/conversation/", hello_conversation_data, format="json"
    )
    b"".join(response.streaming_content)

    assert mock_openai_stream.called
    _assert_turn_lines_carry_ids(json_logs, conversation)


@pytest.mark.asyncio
async def test_turn_lines_carry_ids_async(
    api_client, mock_openai_stream, hello_conversation_data, monkeypatch, json_logs
):
    """Async server mode (ASGI, production)."""
    monkeypatch.setenv("PYTHON_SERVER_MODE", "async")
    conversation = await sync_to_async(ChatConversationFactory)(owner__language="en-us")
    await api_client.aforce_login(conversation.owner)

    response = await sync_to_async(api_client.post)(
        f"/api/v1.0/chats/{conversation.pk}/conversation/", hello_conversation_data, format="json"
    )
    b"".join([chunk async for chunk in response.streaming_content])

    assert mock_openai_stream.called
    _assert_turn_lines_carry_ids(json_logs, conversation)


@pytest.mark.asyncio
async def test_turn_lines_carry_ids_asgi(
    mock_openai_stream, hello_conversation_data, monkeypatch, json_logs
):
    """The real ASGI path: django-structlog's `__acall__`, the view via asgiref."""
    monkeypatch.setenv("PYTHON_SERVER_MODE", "async")
    conversation = await sync_to_async(ChatConversationFactory)(owner__language="en-us")
    client = AsyncClient()
    await client.aforce_login(conversation.owner)

    response = await client.post(
        f"/api/v1.0/chats/{conversation.pk}/conversation/",
        hello_conversation_data,
        content_type="application/json",
    )
    b"".join([chunk async for chunk in response.streaming_content])

    assert mock_openai_stream.called
    _assert_turn_lines_carry_ids(json_logs, conversation)


def test_a_later_request_inherits_nothing_from_a_turn(
    api_client, mock_openai_stream, hello_conversation_data, json_logs
):
    """WSGI serves the next request on the same thread: none of the turn's ids,
    nor its user, may carry over."""
    conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_login(conversation.owner)
    response = api_client.post(
        f"/api/v1.0/chats/{conversation.pk}/conversation/", hello_conversation_data, format="json"
    )
    b"".join(response.streaming_content)
    assert mock_openai_stream.called
    turn_request_id = next(
        line["request_id"] for line in json_logs() if line["logger"] == "chat.turn"
    )
    lines_before = len(json_logs())

    Client().get("/api/v1.0/config/")

    later_lines = json_logs()[lines_before:]
    assert [line["event"] for line in later_lines if line["event"].startswith("request_")] == [
        "request_started",
        "request_finished",
    ]
    # Not every line has a request_id (Dockerflow's summary, unsilenced in tests):
    # what must not happen is one carrying the turn's.
    for line in later_lines:
        assert line.get("request_id") != turn_request_id
        assert line.get("user_id") is None
        assert not [key for key in TURN_IDS if key in line]
