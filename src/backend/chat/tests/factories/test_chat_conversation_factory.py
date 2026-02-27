"""Unit tests for the ChatConversationFactory."""

import pytest

from chat.factories import ChatConversationFactory, ChatProjectFactory

pytestmark = pytest.mark.django_db


def test_conversation_factory():
    """Test that the factory creates a valid conversation with default values."""
    conversation = ChatConversationFactory()

    assert conversation.owner is not None
    assert conversation.title is None
    assert conversation.project is None


def test_conversation_factory_with_project():
    """Test that the factory accepts a project."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(project=project, owner=project.owner)

    assert conversation.project == project
    assert conversation.owner == project.owner
