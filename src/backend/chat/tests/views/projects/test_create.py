"""Unit tests for creating projects."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.models import ChatProject, ChatProjectColor, ChatProjectIcon

pytestmark = pytest.mark.django_db


def test_create_project(api_client):
    """Test creating a new project as an authenticated user."""
    user = UserFactory(sub="testuser", email="test@example.com")
    url = "/api/v1.0/projects/"
    data = {
        "title": "New Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["title"] == "New Project"

    # Verify in database
    project = ChatProject.objects.get(id=response.data["id"])
    assert project.owner == user
    assert project.title == "New Project"
    assert project.icon == ChatProjectIcon.FOLDER
    assert project.color == ChatProjectColor.COLOR_1


def test_create_project_other_owner(api_client):
    """Test that a user cannot assign another user as the owner of a project."""
    other_user = UserFactory()

    user = UserFactory()
    url = "/api/v1.0/projects/"

    data = {
        "title": "New Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
        "owner": str(other_user.pk),  # Attempt to set another user as owner
    }

    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED

    # Verify in database
    project = ChatProject.objects.get(id=response.data["id"])
    assert project.owner == user
    assert project.title == "New Project"


def test_create_project_with_llm_instructions(api_client):
    """Test creating a project with custom llm instructions."""
    user = UserFactory()
    url = "/api/v1.0/projects/"
    data = {
        "title": "New Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
        "llm_instructions": "Always answer in French.",
    }
    api_client.force_login(user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["llm_instructions"] == "Always answer in French."

    project = ChatProject.objects.get(id=response.data["id"])
    assert project.llm_instructions == "Always answer in French."


def test_create_project_anonymous(api_client):
    """Test creating a project as an anonymous user returns a 401 error."""
    url = "/api/v1.0/projects/"
    data = {
        "title": "New Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
