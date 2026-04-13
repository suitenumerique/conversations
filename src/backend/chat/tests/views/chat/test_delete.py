"""Unit tests for chat conversation deletion in the chat API view."""

import logging

import pytest
import responses
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


@pytest.fixture(name="albert_settings")
def fixture_albert_settings(settings):
    """Configure Albert backend so collection cleanup hits a known URL."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


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


@responses.activate
def test_delete_conversation_drops_rag_collection(api_client, albert_settings):
    """Deleting a conversation removes its RAG collection on the backend."""
    conversation = ChatConversationFactory(collection_id="11")
    delete_mock = responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/collections/11",
        status=status.HTTP_204_NO_CONTENT,
    )

    api_client.force_login(conversation.owner)
    response = api_client.delete(f"/api/v1.0/chats/{conversation.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert delete_mock.call_count == 1
    assert not ChatConversation.objects.filter(id=conversation.pk).exists()


@responses.activate
def test_delete_conversation_without_collection_skips_backend(api_client, albert_settings):
    """A conversation that never indexed anything must not call the RAG backend."""
    conversation = ChatConversationFactory(collection_id=None)
    delete_mock = responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/collections/anything",
        status=status.HTTP_204_NO_CONTENT,
    )

    api_client.force_login(conversation.owner)
    response = api_client.delete(f"/api/v1.0/chats/{conversation.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert delete_mock.call_count == 0


@responses.activate
def test_delete_conversation_succeeds_when_backend_fails(api_client, albert_settings, caplog):
    """A backend failure must be logged but must not block the conversation delete."""
    conversation = ChatConversationFactory(collection_id="11")
    responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/collections/11",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    caplog.set_level(logging.ERROR, logger="chat.views")

    api_client.force_login(conversation.owner)
    response = api_client.delete(f"/api/v1.0/chats/{conversation.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not ChatConversation.objects.filter(id=conversation.pk).exists()
    assert any("Failed to delete RAG collection 11" in record.message for record in caplog.records)
