"""Unit tests for retrieving projects."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatProjectFactory

pytestmark = pytest.mark.django_db


def test_retrieve_project(api_client):
    """Test retrieving a project as the owner."""
    project = ChatProjectFactory()

    url = f"/api/v1.0/projects/{project.pk}/"
    api_client.force_login(project.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(project.pk)
    assert response.data["title"] == project.title


def test_retrieve_other_user_project_fails(api_client):
    """Test that retrieving another user's project returns a 404 error."""
    project = ChatProjectFactory()

    other_user = UserFactory()
    url = f"/api/v1.0/projects/{project.pk}/"
    api_client.force_login(other_user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_retrieve_project_anonymous(api_client):
    """Test retrieving a project as an anonymous user returns a 401 error."""
    project = ChatProjectFactory()

    url = f"/api/v1.0/projects/{project.pk}/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
