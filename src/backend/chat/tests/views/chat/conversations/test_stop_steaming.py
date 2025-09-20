"""Test the post_stop_steaming view."""

from unittest.mock import patch

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat import factories
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Set up base settings for the tests."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def test_stop_streaming(api_client):
    """Test that the stop_streaming method is called when the endpoint is called."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    url = f"/api/v1.0/chats/{chat_conversation.pk}/stop-streaming/"

    with patch("chat.clients.pydantic_ai.AIAgentService.stop_streaming") as mock_stop_streaming:
        response = api_client.post(url)
        mock_stop_streaming.assert_called_once_with()

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "OK"}


def test_stop_streaming_unauthenticated(api_client):
    """Test that unauthenticated users cannot call the endpoint."""
    chat_conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/stop-streaming/"

    response = api_client.post(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_stop_streaming_for_conversation_of_another_user(
    api_client,
):
    """Test that a user cannot stop streaming for a conversation of another user."""
    chat_conversation = factories.ChatConversationFactory()
    api_client.force_login(UserFactory())
    url = f"/api/v1.0/chats/{chat_conversation.pk}/stop-streaming/"

    response = api_client.post(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND
