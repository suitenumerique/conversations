"""Unit tests for partial update of projects in the chat API view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatProjectFactory
from chat.models import ChatProjectColor, ChatProjectIcon

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Updated Title"),
        ("icon", ChatProjectIcon.STAR),
        ("color", ChatProjectColor.COLOR_3),
        ("llm_instructions", "Always answer in French."),
    ],
)
def test_partial_update_project(api_client, field, value):
    """Test updating a project field as the owner."""
    project = ChatProjectFactory()

    url = f"/api/v1.0/projects/{project.pk}/"
    data = {field: value}
    api_client.force_login(project.owner)
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data[field] == value

    # Verify in database
    project.refresh_from_db()
    assert getattr(project, field) == value


def test_partial_update_other_user_project_fails(api_client):
    """Test that updating another user's project returns a 404 error."""
    project = ChatProjectFactory()

    other_user = UserFactory()
    url = f"/api/v1.0/projects/{project.pk}/"

    data = {
        "title": "Updated By Other User",
    }
    api_client.force_login(other_user)
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_partial_update_project_anonymous(api_client):
    """Test updating a project as an anonymous user returns a 401 error."""
    project = ChatProjectFactory()

    url = f"/api/v1.0/projects/{project.pk}/"
    data = {
        "title": "Updated Title",
    }
    response = api_client.patch(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
