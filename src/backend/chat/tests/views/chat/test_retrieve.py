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


@pytest.mark.parametrize("pinned_tier", ["simple", None])
def test_retrieve_conversation_exposes_pinned_tier(api_client, pinned_tier):
    """Retrieve exposes the pinned router tier (null for Auto) so the client can
    show it again after a reload instead of releasing it on the next turn."""
    chat_conversation = ChatConversationFactory(pinned_tier=pinned_tier)

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    api_client.force_login(chat_conversation.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["pinned_tier"] == pinned_tier


def test_pinned_tier_is_read_only(api_client):
    """The pin only moves with a turn's `tier`: a conversation update ignores it."""
    chat_conversation = ChatConversationFactory(pinned_tier=None)

    url = f"/api/v1.0/chats/{chat_conversation.pk}/"
    api_client.force_login(chat_conversation.owner)
    response = api_client.patch(url, {"pinned_tier": "complex"}, format="json")

    assert response.status_code == status.HTTP_200_OK
    chat_conversation.refresh_from_db()
    assert chat_conversation.pinned_tier is None


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
