"""Unit tests for project deletion in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatProjectFactory
from chat.models import ChatConversation, ChatProject

pytestmark = pytest.mark.django_db


def test_delete_project(api_client):
    """Test deleting a project as the owner."""
    project = ChatProjectFactory()
    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify deletion in database
    assert not ChatProject.objects.filter(id=project.pk).exists()


def test_delete_project_preserves_conversations(api_client):
    """Test that deleting a project does not delete its conversations."""
    project = ChatProjectFactory(number_of_conversations=1)
    conversation = project.conversations.get()
    api_client.force_login(project.owner)
    response = api_client.delete(f"/api/v1.0/projects/{project.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not ChatProject.objects.filter(id=project.pk).exists()

    # still exists despite project deletion
    assert ChatConversation.objects.filter(pk=conversation.pk).exists()


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
