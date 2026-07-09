"""Unit tests for the conversation language carried by AIAgentService."""
# pylint: disable=protected-access

import pytest

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db


def test_language_reaches_the_tool_dependencies():
    """The UI language must reach the tools, which resolve a search market from it."""
    conversation = ChatConversationFactory()

    service = AIAgentService(conversation, user=conversation.owner, language="fr-fr")

    assert service.language == "fr-fr"
    assert service._context_deps.language == "fr-fr"


def test_language_defaults_to_none():
    """Without a language the deps carry None, letting the tools fall back to LANGUAGE_CODE."""
    conversation = ChatConversationFactory()

    service = AIAgentService(conversation, user=conversation.owner)

    assert service.language is None
    assert service._context_deps.language is None
