"""Unit tests for listing chat conversations in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_list_conversations(api_client):
    """Test retrieving the list of chat conversations for an authenticated user."""
    chat_conversation = ChatConversationFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(chat_conversation.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["id"] == str(chat_conversation.pk)
    assert response.data["results"][0]["title"] == chat_conversation.title


def test_list_conversations_empty(api_client):
    """Test retrieving an empty list for a user with no conversations."""
    other_user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(other_user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 0


def test_list_conversations_anonymous(api_client):
    """Test listing conversations as an anonymous user returns a 401 error."""
    url = "/api/v1.0/chats/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_filter_conversations_by_title(api_client):
    """Test filtering conversations by title substring."""
    user = UserFactory(sub="testuser", email="test@example.com")
    ChatConversation.objects.create(
        owner=user,
        title="Test Conversation",
        ui_messages=[{"role": "user", "content": "Test message"}],
    )
    ChatConversation.objects.create(owner=user, title="Another Conversation", ui_messages=[])
    url = "/api/v1.0/chats/?title=Test"
    api_client.force_login(user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["title"] == "Test Conversation"


def test_ordering_conversations(api_client):
    """Test ordering conversations by creation date."""
    user = UserFactory(sub="testuser", email="test@example.com")
    conv1 = ChatConversation.objects.create(owner=user, title="First Conversation", ui_messages=[])
    conv2 = ChatConversation.objects.create(owner=user, title="Second Conversation", ui_messages=[])
    url = "/api/v1.0/chats/"
    api_client.force_login(user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["id"] == str(conv2.id)
    assert response.data["results"][1]["id"] == str(conv1.id)

    url = "/api/v1.0/chats/?ordering=created_at"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["id"] == str(conv1.id)
    assert response.data["results"][1]["id"] == str(conv2.id)
