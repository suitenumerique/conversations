"""Tests for the request body size cap on the chat endpoint."""

import io
import json

import pytest
from rest_framework import status

from chat.factories import ChatConversationFactory
from chat.parsers import RequestBodyTooLarge, SizeLimitedJSONParser
from chat.tests.utils import assert_data_stream_response

pytestmark = pytest.mark.django_db(transaction=True)


def test_post_conversation_body_over_limit_is_refused(
    api_client, settings, hello_conversation_data
):
    """A body one byte over the limit gets a 413 and the conversation is left untouched."""
    conversation = ChatConversationFactory()
    body = json.dumps(hello_conversation_data)
    settings.CHAT_REQUEST_MAX_BODY_SIZE = len(body) - 1
    api_client.force_login(conversation.owner)

    response = api_client.post(
        f"/api/v1.0/chats/{conversation.pk}/conversation/",
        body,
        content_type="application/json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "Request body too large."}
    updated_at = conversation.updated_at
    conversation.refresh_from_db()
    assert conversation.messages == []
    assert conversation.pydantic_messages == []
    assert conversation.updated_at == updated_at


def test_post_conversation_body_at_limit_is_accepted(
    api_client, settings, mock_openai_stream, hello_conversation_data
):
    """A body exactly at the limit goes through to the model."""
    conversation = ChatConversationFactory()
    body = json.dumps(hello_conversation_data)
    settings.CHAT_REQUEST_MAX_BODY_SIZE = len(body)
    api_client.force_login(conversation.owner)

    response = api_client.post(
        f"/api/v1.0/chats/{conversation.pk}/conversation/",
        body,
        content_type="application/json",
    )

    assert_data_stream_response(response)
    b"".join(response.streaming_content)
    assert mock_openai_stream.called


def test_parser_bounds_a_body_without_declared_length(settings):
    """The cap holds on the bytes read, so a chunked body with no Content-Length is bounded."""
    settings.CHAT_REQUEST_MAX_BODY_SIZE = 10
    stream = io.BytesIO(b'{"messages": []}')

    with pytest.raises(RequestBodyTooLarge):
        SizeLimitedJSONParser().parse(stream)

    # One byte past the limit is all it reads.
    assert stream.tell() == 11
