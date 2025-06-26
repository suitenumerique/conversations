"""Unit tests for updating chat conversations in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_update_conversation(api_client):
    """Test updating a chat conversation as the owner."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    data = {"title": "Updated Title"}
    api_client.force_login(chat_conversation.owner)
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Updated Title"

    # Verify in database
    conversation = ChatConversation.objects.get(id=chat_conversation.pk)
    assert conversation.title == "Updated Title"


def test_update_conversation_anonymous(api_client):
    """Test updating a conversation as an anonymous user returns a 401 error."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    data = {"title": "Updated Title"}
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_update_other_user_conversation_fails(api_client):
    """Test that updating another user's conversation returns a 404 error."""
    chat_conversation = ChatConversationFactory()

    other_user = UserFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    data = {"title": "Updated By Other User"}
    api_client.force_login(other_user)
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
