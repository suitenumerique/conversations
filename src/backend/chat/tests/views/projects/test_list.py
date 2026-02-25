"""Unit tests for listing projects in the chat API view."""

import pytest
from freezegun import freeze_time
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory, ChatProjectFactory

pytestmark = pytest.mark.django_db


def test_list_projects(api_client, django_assert_num_queries):
    """Test retrieving the list of projects for an authenticated user."""
    project = ChatProjectFactory()
    url = "/api/v1.0/projects/"
    api_client.force_login(project.owner)

    with django_assert_num_queries(4):
        response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["id"] == str(project.pk)
    assert results[0]["title"] == project.title
    assert results[0]["conversations"] == []


def test_filter_projects_by_title(api_client):
    """Test filtering projects by title substring."""
    user = UserFactory(sub="testuser", email="test@example.com")

    ChatProjectFactory(owner=user, title="Test Project")

    ChatProjectFactory(owner=user, title="Other Project")

    url = "/api/v1.0/projects/?title=Test"
    api_client.force_login(user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["title"] == "Test Project"


def test_list_projects_with_conversations(api_client, django_assert_num_queries):
    """Test retrieving projects with associated conversations ordered by -created_at."""
    project = ChatProjectFactory()

    with freeze_time("2026-01-01"):
        conversation_1 = ChatConversationFactory(
            project=project, owner=project.owner, title="My conversation 1"
        )
    with freeze_time("2026-01-02"):
        conversation_2 = ChatConversationFactory(
            project=project, owner=project.owner, title="My conversation 2"
        )

    url = "/api/v1.0/projects/"
    api_client.force_login(project.owner)

    with django_assert_num_queries(4):
        response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["id"] == str(project.pk)
    assert results[0]["title"] == project.title
    assert results[0]["conversations"] == [
        {
            "id": str(conversation_2.id),
            "title": conversation_2.title,
        },
        {
            "id": str(conversation_1.id),
            "title": conversation_1.title,
        },
    ]


def test_list_projects_no_n_plus_one(api_client, django_assert_num_queries):
    """Test that query count stays constant regardless of project/conversation count."""
    user = UserFactory()
    for _ in range(3):
        ChatProjectFactory(owner=user, number_of_conversations=2)

    url = "/api/v1.0/projects/"
    api_client.force_login(user)

    with django_assert_num_queries(4):
        response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 3


def test_list_projects_ordered_by_title(api_client):
    """Test that projects are returned in alphabetical order by title."""
    user = UserFactory()
    ChatProjectFactory(owner=user, title="Zeta")
    ChatProjectFactory(owner=user, title="Alpha")
    ChatProjectFactory(owner=user, title="Mu")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/projects/")

    assert response.status_code == status.HTTP_200_OK
    titles = [r["title"] for r in response.data["results"]]
    assert titles == ["Alpha", "Mu", "Zeta"]


@pytest.mark.parametrize(
    "ordering,expected_titles",
    [
        ("created_at", ["First", "Second", "Third"]),
        ("-created_at", ["Third", "Second", "First"]),
        ("title", ["First", "Second", "Third"]),
        ("-title", ["Third", "Second", "First"]),
    ],
)
def test_list_projects_ordering(api_client, ordering, expected_titles):
    """Test ordering projects by the allowed ordering fields."""
    user = UserFactory()
    with freeze_time("2026-01-01"):
        ChatProjectFactory(owner=user, title="First")
    with freeze_time("2026-01-02"):
        ChatProjectFactory(owner=user, title="Second")
    with freeze_time("2026-01-03"):
        ChatProjectFactory(owner=user, title="Third")

    api_client.force_login(user)
    response = api_client.get(f"/api/v1.0/projects/?ordering={ordering}")

    assert response.status_code == status.HTTP_200_OK
    titles = [r["title"] for r in response.data["results"]]
    assert titles == expected_titles


def test_list_projects_ordering_by_updated_at(api_client):
    """Test ordering projects by updated_at."""
    user = UserFactory()
    with freeze_time("2026-01-01"):
        project_a = ChatProjectFactory(owner=user, title="A")
        ChatProjectFactory(owner=user, title="B")
    with freeze_time("2026-01-02"):
        project_a.title = "A updated"
        project_a.save()

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/projects/?ordering=updated_at")

    assert response.status_code == status.HTTP_200_OK
    titles = [r["title"] for r in response.data["results"]]
    assert titles == ["B", "A updated"]


def test_list_projects_empty(api_client):
    """Test retrieving the list of projects for an authenticated user."""
    user = UserFactory()
    url = "/api/v1.0/projects/"
    api_client.force_login(user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 0


def test_list_projects_anonymous(api_client):
    """Test listing projects as an anonymous user returns a 401 error."""

    url = "/api/v1.0/projects/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
