"""Unit tests for project deletion in the chat API view."""

import logging

import pytest
import responses
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatProjectFactory
from chat.models import ChatConversation, ChatProject

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


def test_delete_project(api_client):
    """Test deleting a project as the owner."""
    project = ChatProjectFactory()
    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify deletion in database
    assert not ChatProject.objects.filter(id=project.pk).exists()


def test_delete_project_deletes_related_conversations(api_client):
    """Test that deleting a project also deletes its conversations."""
    project = ChatProjectFactory(number_of_conversations=2)
    conversation_pks = list(project.conversations.values_list("pk", flat=True))
    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not ChatProject.objects.filter(id=project.pk).exists()
    assert not ChatConversation.objects.filter(pk__in=conversation_pks).exists()


def test_delete_project_does_not_affect_other_conversations(api_client):
    """Test that deleting a project does not delete conversations from other projects."""
    project = ChatProjectFactory(number_of_conversations=1)
    other_project = ChatProjectFactory(owner=project.owner, number_of_conversations=1)
    other_conversation = other_project.conversations.get()

    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert ChatConversation.objects.filter(pk=other_conversation.pk).exists()


def test_delete_other_user_project_fails(api_client):
    """Test that deleting another user's project returns a 404 error."""
    project = ChatProjectFactory()
    other_user = UserFactory()
    api_client.force_login(other_user)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Verify project still exists
    assert ChatProject.objects.filter(id=project.pk).exists()


def test_delete_project_user_anonymous(api_client):
    """Test deleting a project as an anonymous user returns a 401 error."""
    project = ChatProjectFactory()
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # Verify project still exists
    assert ChatProject.objects.filter(id=project.pk).exists()


@responses.activate
def test_delete_project_drops_rag_collection(api_client, albert_settings):
    """Deleting a project removes its RAG collection on the backend."""
    project = ChatProjectFactory(collection_id="42")
    delete_mock = responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/collections/42",
        status=status.HTTP_204_NO_CONTENT,
    )

    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert delete_mock.call_count == 1
    assert not ChatProject.objects.filter(id=project.pk).exists()


@responses.activate
def test_delete_project_without_collection_skips_backend(api_client, albert_settings):
    """A project that never indexed anything must not call the RAG backend."""
    project = ChatProjectFactory(collection_id=None)
    delete_mock = responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/collections/anything",
        status=status.HTTP_204_NO_CONTENT,
    )

    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert delete_mock.call_count == 0
    assert not ChatProject.objects.filter(id=project.pk).exists()


@responses.activate
def test_delete_project_succeeds_when_backend_fails(api_client, albert_settings, caplog):
    """A backend failure must be logged but must not block the project delete."""
    project = ChatProjectFactory(collection_id="42")
    responses.delete(
        f"{albert_settings.ALBERT_API_URL}/v1/collections/42",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    caplog.set_level(logging.ERROR, logger="chat.views")

    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not ChatProject.objects.filter(id=project.pk).exists()
    assert any("Failed to delete RAG collection 42" in record.message for record in caplog.records)
