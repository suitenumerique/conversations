"""Unit tests for retrieving chat conversations in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory, ChatProjectFactory

pytestmark = pytest.mark.django_db


def test_retrieve_conversation(api_client):
    """Test retrieving a single chat conversation as the owner."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    api_client.force_login(chat_conversation.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(chat_conversation.pk)
    assert response.data["title"] == chat_conversation.title


def test_retrieve_conversation_nests_project(api_client):
    """Retrieve nests the project as {id, title, icon} (not a bare id) so the
    client can read the conversation's project without a second request."""
    project = ChatProjectFactory()
    chat_conversation = ChatConversationFactory(project=project, owner=project.owner)

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    api_client.force_login(project.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["project"] == {
        "id": str(project.pk),
        "title": project.title,
        "icon": project.icon,
    }


def test_retrieve_conversation_without_project(api_client):
    """Retrieve returns project=None for a conversation with no project."""
    chat_conversation = ChatConversationFactory(project=None)

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    api_client.force_login(chat_conversation.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["project"] is None


def test_retrieve_other_user_conversation_fails(api_client):
    """Test that retrieving another user's conversation returns a 404 error."""
    chat_conversation = ChatConversationFactory()

    other_user = UserFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    api_client.force_login(other_user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_retrieve_conversation_anonymous(api_client):
    """Test retrieving a conversation as an anonymous user returns a 401 error."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
