"""Unit tests for listing chat conversations in the chat API view."""

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db


def test_list_conversations(api_client):
    """Test retrieving the list of chat conversations for an authenticated user."""
    chat_conversation = ChatConversationFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(chat_conversation.owner)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["id"] == str(chat_conversation.pk)
    assert response.data["results"][0]["title"] == chat_conversation.title


def test_list_conversations_empty(api_client):
    """Test retrieving an empty list for a user with no conversations."""
    other_user = UserFactory()
    url = "/api/v1.0/chats/"
    api_client.force_login(other_user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 0


def test_list_conversations_anonymous(api_client):
    """Test listing conversations as an anonymous user returns a 401 error."""
    url = "/api/v1.0/chats/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_filter_conversations_by_title(api_client):
    """Test filtering conversations by title substring."""
    user = UserFactory(sub="testuser", email="test@example.com")
    ChatConversation.objects.create(owner=user, title="Test Conversation")
    ChatConversation.objects.create(owner=user, title="Another Conversation")
    url = "/api/v1.0/chats/?title=Test"
    api_client.force_login(user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["title"] == "Test Conversation"


def test_ordering_conversations(api_client):
    """Test ordering conversations by creation date."""
    user = UserFactory(sub="testuser", email="test@example.com")
    conv1 = ChatConversation.objects.create(owner=user, title="First Conversation")
    conv2 = ChatConversation.objects.create(owner=user, title="Second Conversation")
    url = "/api/v1.0/chats/"
    api_client.force_login(user)
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["id"] == str(conv2.id)
    assert response.data["results"][1]["id"] == str(conv1.id)

    url = "/api/v1.0/chats/?ordering=created_at"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["id"] == str(conv1.id)
    assert response.data["results"][1]["id"] == str(conv2.id)


def test_list_conversations_no_project_filter_returns_all(api_client):
    """Test that without project filter, all conversations are returned."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    conv_in_project = ChatConversationFactory(owner=user, project=project, title="In project")
    conv_no_project = ChatConversationFactory(owner=user, title="No project")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2
    result_ids = {r["id"] for r in response.data["results"]}
    assert result_ids == {str(conv_in_project.pk), str(conv_no_project.pk)}


def test_filter_conversations_by_project(api_client):
    """Test filtering conversations by a specific project."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    conv_in_project = ChatConversationFactory(owner=user, project=project, title="In project")
    ChatConversationFactory(owner=user, title="No project")

    api_client.force_login(user)
    response = api_client.get(f"/api/v1.0/chats/?project={project.pk}")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["id"] == str(conv_in_project.pk)


def test_filter_conversations_by_project_invalid_uuid(api_client):
    """Test that an invalid UUID for project filter returns empty results."""
    user = UserFactory()
    ChatConversationFactory(owner=user, title="Some chat")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/?project=notauuid")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 0


def test_filter_conversations_by_project_none(api_client):
    """Test filtering conversations not linked to any project."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    ChatConversationFactory(owner=user, project=project, title="In project")
    conv_no_project = ChatConversationFactory(owner=user, title="No project")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/?project=none")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["id"] == str(conv_no_project.pk)


def test_filter_conversations_by_project_any(api_client):
    """Test filtering conversations linked to any project."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    conv_in_project = ChatConversationFactory(owner=user, project=project, title="In project")
    ChatConversationFactory(owner=user, title="No project")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/?project=any")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["id"] == str(conv_in_project.pk)


def test_filter_conversations_by_title_and_project(api_client):
    """Test filtering conversations by both title and project."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    conv_match = ChatConversationFactory(owner=user, project=project, title="Design review")
    ChatConversationFactory(owner=user, project=project, title="Budget plan")
    ChatConversationFactory(owner=user, title="Design ideas")

    api_client.force_login(user)
    response = api_client.get(f"/api/v1.0/chats/?title=Design&project={project.pk}")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["id"] == str(conv_match.pk)


def test_search_by_title_returns_nested_project_info(api_client):
    """Test that searching by title returns nested project info (id, title, icon)."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user, title="My Project", icon="folder")
    conv = ChatConversationFactory(owner=user, project=project, title="Hello world")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/?title=Hello")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    result = response.data["results"][0]
    assert result["id"] == str(conv.pk)
    assert result["project"] == {
        "id": str(project.pk),
        "title": "My Project",
        "icon": "folder",
    }
    assert "messages" not in result


def test_search_by_title_returns_null_project_when_none(api_client):
    """Test that searching by title for a conversation without a project returns null."""
    user = UserFactory()
    conv = ChatConversationFactory(owner=user, title="Standalone chat")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/?title=Standalone")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    result = response.data["results"][0]
    assert result["id"] == str(conv.pk)
    assert result["project"] is None


def test_list_without_title_filter_does_not_nest_project(api_client):
    """Test that listing without title filter returns project as a UUID, not nested."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    ChatConversationFactory(owner=user, project=project, title="Some chat")

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    result = response.data["results"][0]
    # project should be a flat UUID, not a nested dict
    assert not isinstance(result["project"], dict)
    assert str(result["project"]) == str(project.pk)


def test_list_leaves_message_history_out(api_client):
    """The sidebar list returns the listing fields only, not the history."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)

    api_client.force_login(user)
    response = api_client.get("/api/v1.0/chats/?project=none")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["results"] == [
        {
            "id": str(conversation.pk),
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": conversation.updated_at.isoformat().replace("+00:00", "Z"),
            "project": None,
        }
    ]


def test_list_does_not_load_heavy_columns(api_client):
    """Listing reads neither the JSON columns nor the project-image subquery."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    ChatConversationFactory.create_batch(3, owner=user)
    ChatConversationFactory.create_batch(2, owner=user, project=project)

    api_client.force_login(user)
    with CaptureQueriesContext(connection) as queries:
        response = api_client.get("/api/v1.0/chats/?ordering=-updated_at&project=none")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["results"]) == 3
    listing = [q["sql"] for q in queries if 'FROM "chat_chatconversation"' in q["sql"]]
    assert listing
    for sql in listing:
        # Same predicate as the partial owner/updated_at index
        assert '"chat_chatconversation"."project_id" IS NULL' in sql
        for column in ("pydantic_messages", '"messages"', "agent_usage"):
            assert column not in sql
        assert "chat_chatconversationattachment" not in sql


def test_search_list_loads_nested_project_without_extra_queries(api_client):
    """Title search keeps its nested project while deferring the heavy columns."""
    user = UserFactory()
    project = ChatProjectFactory(owner=user, title="Proj")
    ChatConversationFactory.create_batch(3, owner=user, project=project, title="Match me")

    api_client.force_login(user)
    with CaptureQueriesContext(connection) as queries:
        response = api_client.get("/api/v1.0/chats/?title=match")

    assert response.status_code == status.HTTP_200_OK
    assert [result["project"]["title"] for result in response.json()["results"]] == ["Proj"] * 3
    assert not any('"chat_chatproject"."id" = ' in q["sql"] for q in queries)
