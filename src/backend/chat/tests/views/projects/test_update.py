"""Unit tests for updating projects in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatProjectFactory
from chat.models import ChatProjectColor, ChatProjectIcon

pytestmark = pytest.mark.django_db


def test_update_project(api_client):
    """Test updating a project as the owner."""
    project = ChatProjectFactory()

    url = f"/api/v1.0/projects/{project.pk}/"
    data = {
        "title": "Updated Title",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    api_client.force_login(project.owner)
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Updated Title"

    # Verify in database
    project.refresh_from_db()
    assert project.title == "Updated Title"


def test_update_project_llm_instructions(api_client):
    """Test updating a project's LLM instructions via PUT."""
    project = ChatProjectFactory(llm_instructions="Old instructions")

    url = f"/api/v1.0/projects/{project.pk}/"
    data = {
        "title": project.title,
        "icon": project.icon,
        "color": project.color,
        "llm_instructions": "New instructions",
    }
    api_client.force_login(project.owner)
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["llm_instructions"] == "New instructions"

    project.refresh_from_db()
    assert project.llm_instructions == "New instructions"


def test_update_other_user_project_fails(api_client):
    """Test that updating another user's project returns a 404 error."""
    project = ChatProjectFactory()

    other_user = UserFactory()
    url = f"/api/v1.0/projects/{project.pk}/"

    data = {
        "title": "Updated By Other User",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    api_client.force_login(other_user)
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_project_anonymous(api_client):
    """Test updating a project as an anonymous user returns a 401 error."""
    project = ChatProjectFactory()

    url = f"/api/v1.0/projects/{project.pk}/"
    data = {
        "title": "Updated Title",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    response = api_client.put(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
