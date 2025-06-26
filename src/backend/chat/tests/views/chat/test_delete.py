"""Unit tests for chat conversation deletion in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_delete_conversation(api_client):
    """Test deleting a chat conversation as the owner."""
    chat_conversation = ChatConversationFactory()
    api_client.force_login(chat_conversation.owner)
    response = api_client.delete(f"/api/v1.0/chats/{chat_conversation.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify deletion in database
    assert not ChatConversation.objects.filter(id=chat_conversation.pk).exists()


def test_delete_other_user_conversation_fails(api_client):
    """Test that deleting another user's conversation returns a 404 error."""
    chat_conversation = ChatConversationFactory()
    other_user = UserFactory()
    api_client.force_login(other_user)
    response = api_client.delete(f"/api/v1.0/chats/{chat_conversation.pk}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Verify conversation still exists
    assert ChatConversation.objects.filter(id=chat_conversation.pk).exists()


def test_delete_conversation_anonymous(api_client):
    """Test deleting a conversation as an anonymous user returns a 401 error."""
    chat_conversation = ChatConversationFactory()
    response = api_client.delete(f"/api/v1.0/chats/{chat_conversation.pk}/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # Verify conversation still exists
    assert ChatConversation.objects.filter(id=chat_conversation.pk).exists()
