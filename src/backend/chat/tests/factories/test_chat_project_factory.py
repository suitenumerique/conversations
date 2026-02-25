"""Unit tests for the ChatProjectFactory."""

import pytest

from chat.factories import ChatProjectFactory
from chat.models import ChatProjectColor, ChatProjectIcon

pytestmark = pytest.mark.django_db


def test_project_factory():
    """Test that the factory creates a valid project with default values."""
    project = ChatProjectFactory()

    assert project.title.startswith("title ")
    assert project.icon == ChatProjectIcon.FOLDER
    assert project.color == ChatProjectColor.COLOR_1
    assert project.owner is not None
    assert project.conversations.count() == 0


def test_project_factory_number_of_conversations():
    """Test that number_of_conversations creates attached conversations."""
    project = ChatProjectFactory(number_of_conversations=3)

    assert project.conversations.count() == 3
    assert all(c.owner == project.owner for c in project.conversations.all())
