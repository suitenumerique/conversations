"""Unit tests for the ChatProjectSerializer."""

import pytest
from rest_framework.test import APIRequestFactory

from core.factories import UserFactory

from chat import serializers
from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.models import ChatProjectColor, ChatProjectIcon

pytestmark = pytest.mark.django_db


@pytest.fixture(name="request_context")
def request_context_fixture():
    """Return a serializer context with an authenticated request."""
    user = UserFactory()
    request = APIRequestFactory().post("/")
    request.user = user
    return {"request": request}


def test_serialize_project():
    """Test serializing a project returns expected fields."""
    project = ChatProjectFactory()
    serializer = serializers.ChatProjectSerializer(project)
    data = serializer.data

    assert data["id"] == str(project.pk)
    assert data["title"] == project.title
    assert data["icon"] == project.icon
    assert data["color"] == project.color
    assert data["llm_instructions"] == project.llm_instructions
    assert data["conversations"] == []
    assert "created_at" in data
    assert "updated_at" in data


def test_serialize_project_with_conversations():
    """Test serializing a project includes nested conversations."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(
        project=project, owner=project.owner, title="My conversation"
    )
    serializer = serializers.ChatProjectSerializer(project)
    data = serializer.data

    assert len(data["conversations"]) == 1
    assert data["conversations"][0] == {
        "id": str(conversation.pk),
        "title": "My conversation",
    }


def test_deserialize_valid_project(request_context):
    """Test deserializing valid project data."""
    data = {
        "title": "My Project",
        "icon": ChatProjectIcon.STAR,
        "color": ChatProjectColor.COLOR_2,
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert serializer.is_valid()
    assert serializer.validated_data["title"] == "My Project"
    assert serializer.validated_data["icon"] == ChatProjectIcon.STAR
    assert serializer.validated_data["color"] == ChatProjectColor.COLOR_2


def test_deserialize_missing_title(request_context):
    """Test that title is required."""
    data = {
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert not serializer.is_valid()
    assert "title" in serializer.errors


def test_deserialize_invalid_icon(request_context):
    """Test that an invalid icon value is rejected."""
    data = {
        "title": "My Project",
        "icon": "invalid_icon",
        "color": ChatProjectColor.COLOR_1,
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert not serializer.is_valid()
    assert "icon" in serializer.errors


def test_deserialize_invalid_color(request_context):
    """Test that an invalid color value is rejected."""
    data = {
        "title": "My Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": "invalid_color",
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert not serializer.is_valid()
    assert "color" in serializer.errors


def test_deserialize_title_max_length(request_context):
    """Test that a title exceeding 100 characters is rejected."""
    data = {
        "title": "X" * 101,
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert not serializer.is_valid()
    assert "title" in serializer.errors


def test_conversations_field_is_read_only(request_context):
    """Test that conversations cannot be set via input data."""
    data = {
        "title": "My Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
        "conversations": [{"id": "fake", "title": "fake"}],
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert serializer.is_valid()
    assert "conversations" not in serializer.validated_data


def test_owner_is_set_from_request(request_context):
    """Test that the owner is automatically set from the request user."""
    data = {
        "title": "My Project",
        "icon": ChatProjectIcon.FOLDER,
        "color": ChatProjectColor.COLOR_1,
    }
    serializer = serializers.ChatProjectSerializer(data=data, context=request_context)

    assert serializer.is_valid()
    project = serializer.save()
    assert project.owner == request_context["request"].user
