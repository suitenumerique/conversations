"""Test the post_score_message view."""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat import factories

pytestmark = pytest.mark.django_db()


def test_score_message_with_positive_sentiment(api_client):
    """Test scoring a message with positive sentiment."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    trace_id = "test-trace-123"
    message_id = f"trace-{trace_id}"

    with patch("langfuse.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = api_client.post(
            url,
            data={
                "message_id": message_id,
                "value": "positive",
            },
            format="json",
        )

        mock_client.create_score.assert_called_once_with(
            name="sentiment",
            value="positive",
            trace_id=trace_id,
            score_id=f"{trace_id}-{chat_conversation.owner.pk}",
            data_type="CATEGORICAL",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "OK"}


def test_score_message_with_negative_sentiment(api_client):
    """Test scoring a message with negative sentiment."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    trace_id = "test-trace-456"
    message_id = f"trace-{trace_id}"

    with patch("langfuse.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = api_client.post(
            url,
            data={
                "message_id": message_id,
                "value": "negative",
            },
            format="json",
        )

        mock_client.create_score.assert_called_once_with(
            name="sentiment",
            value="negative",
            trace_id=trace_id,
            score_id=f"{trace_id}-{chat_conversation.owner.pk}",
            data_type="CATEGORICAL",
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "OK"}


def test_score_message_without_trace_prefix(api_client):
    """Test that scoring fails when message_id doesn't have trace prefix."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    with patch("langfuse.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = api_client.post(
            url,
            data={
                "message_id": "invalid-message-id",
                "value": "positive",
            },
            format="json",
        )

        # Should not call create_score if validation fails
        mock_client.create_score.assert_not_called()

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid message_id, no trace attached." in str(response.data)


def test_score_message_with_invalid_value(api_client):
    """Test that scoring fails with an invalid sentiment value."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    response = api_client.post(
        url,
        data={
            "message_id": "trace-test-123",
            "value": "invalid_sentiment",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_score_message_missing_message_id(api_client):
    """Test that scoring fails when message_id is missing."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    response = api_client.post(
        url,
        data={
            "value": "positive",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_score_message_missing_value(api_client):
    """Test that scoring fails when value is missing."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    response = api_client.post(
        url,
        data={
            "message_id": "trace-test-123",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_score_message_unauthenticated(api_client):
    """Test that unauthenticated users cannot score messages."""
    chat_conversation = factories.ChatConversationFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    response = api_client.post(
        url,
        data={
            "message_id": "trace-test-123",
            "value": "positive",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_score_message_for_conversation_of_another_user(api_client):
    """Test that a user cannot score messages in a conversation of another user."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(UserFactory())
    url = f"/api/v1.0/chats/{chat_conversation.pk}/score-message/"

    response = api_client.post(
        url,
        data={
            "message_id": "trace-test-123",
            "value": "positive",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_score_message_for_nonexistent_conversation(api_client):
    """Test that scoring fails for a non-existent conversation."""
    user = UserFactory()
    api_client.force_login(user)
    url = "/api/v1.0/chats/99999/score-message/"

    response = api_client.post(
        url,
        data={
            "message_id": "trace-test-123",
            "value": "positive",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
