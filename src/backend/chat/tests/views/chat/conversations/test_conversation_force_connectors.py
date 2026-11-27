"""`force_connectors`: the connectors a turn demands, carried by the request alone."""

from unittest.mock import patch

import pytest
from rest_framework import status

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db


def _post(api_client, conversation, query, payload):
    """POST a turn and return the forces handed to the agent."""
    api_client.force_login(conversation.owner)
    with patch.object(AIAgentService, "stream_data", return_value=iter([])) as stream_data:
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/{query}", payload, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        _ = b"".join(response.streaming_content)
    return stream_data.call_args.kwargs["force_connectors"]


def test_each_forced_connector_reaches_the_agent(api_client, hello_conversation_data):
    """One query parameter per connector, in order."""
    conversation = ChatConversationFactory()

    forced = _post(
        api_client,
        conversation,
        "?force_connectors=datagouv&force_connectors=sofia",
        hello_conversation_data,
    )

    assert forced == ["datagouv", "sofia"]


def test_nothing_forced_by_default(api_client, hello_conversation_data):
    """A turn forces no connector unless it says so."""
    conversation = ChatConversationFactory()

    assert _post(api_client, conversation, "", hello_conversation_data) == []


def test_an_unknown_slug_does_not_fail_the_turn(api_client, hello_conversation_data):
    """A stale force kept in the browser is dropped by the turn, not refused here."""
    conversation = ChatConversationFactory()

    assert _post(api_client, conversation, "?force_connectors=gone", hello_conversation_data) == [
        "gone"
    ]


def test_the_force_is_never_stored(api_client, hello_conversation_data):
    """Not on the conversation, not on the message: it lives in the request only."""
    conversation = ChatConversationFactory()

    _post(api_client, conversation, "?force_connectors=datagouv", hello_conversation_data)

    conversation.refresh_from_db()
    assert "force_connectors" not in str(conversation.messages)
    assert "force_connectors" not in str(conversation.pydantic_messages)
