"""Unit tests for partially updating chat conversations in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_partial_update_conversation_title(api_client):
    """Test partially updating a chat conversation title as the owner."""
    chat_conversation = ChatConversationFactory(title="Original Title")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    data = {"title": "Updated Title"}
    api_client.force_login(chat_conversation.owner)
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Updated Title"

    conversation = ChatConversation.objects.get(id=chat_conversation.pk)
    assert conversation.title == "Updated Title"
    assert conversation.title_set_by_user_at


def test_partial_update_conversation_anonymous(api_client):
    """Test partially updating a conversation as an anonymous user returns a 401 error."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    data = {"title": "Updated Title"}
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_partial_update_conversation_project_fails(api_client):
    """Test that partially updating a conversation's project is rejected."""
    conversation = ChatConversationFactory()
    project = ChatProjectFactory(owner=conversation.owner)

    url = f"/api/v1.0/chats/{conversation.pk}/"
    data = {"project": str(project.pk)}
    api_client.force_login(conversation.owner)
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "project" in response.data

    conversation.refresh_from_db()
    assert conversation.project is None


def test_partial_update_other_user_conversation_fails(api_client):
    """Test that partially updating another user's conversation returns a 404 error."""
    chat_conversation = ChatConversationFactory()

    other_user = UserFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    data = {"title": "Updated By Other User"}
    api_client.force_login(other_user)
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
