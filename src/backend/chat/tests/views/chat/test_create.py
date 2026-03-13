"""Unit tests for chat conversation creation in the chat API view."""

import pytest
from rest_framework import status
from rest_framework.exceptions import ErrorDetail

from core.factories import UserFactory

from chat.factories import ChatProjectFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_create_conversation(api_client):
    """Test creating a new chat conversation as an authenticated user."""
    user = UserFactory(sub="testuser", email="test@example.com")
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["title"] == "New Conversation"
    assert response.data["messages"] == []

    # Verify in database
    conversation = ChatConversation.objects.get(id=response.data["id"])
    assert conversation.owner == user
    assert conversation.title == "New Conversation"
    assert not conversation.title_set_by_user_at


def test_create_conversation_other_owner(api_client):
    """Test that a user cannot assign another user as the owner of a conversation."""
    other_user = UserFactory()

    user = UserFactory()
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
        "owner": str(other_user.pk),  # Attempt to set another user as owner
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED

    # Verify in database
    conversation = ChatConversation.objects.get(id=response.data["id"])
    assert conversation.owner == user
    assert conversation.title == "New Conversation"


def test_create_conversation_with_project(api_client):
    """Test creating a conversation attached to a project."""
    project = ChatProjectFactory()
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
        "project": str(project.pk),
    }
    api_client.force_login(project.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert str(response.data["project"]) == str(project.pk)

    conversation = ChatConversation.objects.get(id=response.data["id"])
    assert conversation.project == project


def test_create_conversation_with_other_user_project_fails(api_client):
    """Test that creating a conversation with another user's project is rejected."""
    user = UserFactory()
    other_project = ChatProjectFactory()  # owned by another user
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
        "project": str(other_project.pk),
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    assert response.data == {
        "project": [
            ErrorDetail(
                string="The project must belong to the current user.",
                code="invalid",
            )
        ]
    }


def test_create_conversation_without_project(api_client):
    """Test creating a conversation without a project."""
    user = UserFactory()
    url = "/api/v1.0/chats/"
    data = {"title": "New Conversation"}
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["project"] is None


def test_create_conversation_anonymous(api_client):
    """Test creating a conversation as an anonymous user returns a 401 error."""
    url = "/api/v1.0/chats/"
    data = {
        "title": "New Conversation",
    }
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
