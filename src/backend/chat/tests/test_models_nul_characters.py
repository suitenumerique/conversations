"""Tests for NUL characters in conversation fields, which Postgres text and jsonb reject."""

import pytest

from chat import models
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


def test_nul_characters_are_stripped():
    """NUL characters in text, nested values and keys are stripped, even when `save` is bypassed."""
    conversation = ChatConversationFactory()
    models.ChatConversation.objects.filter(pk=conversation.pk).update(
        title="a\x00b",
        history_summary="a\x00b",
        ui_messages=[{"content\x00": ["a\x00b"]}],
        messages=[
            UIMessage(id="msg-1", role="assistant", parts=[TextUIPart(type="text", text="a\x00b")])
        ],
    )
    chunk = models.ChatStreamChunk.objects.create(conversation=conversation, seq=0, text="a\x00b")

    conversation.refresh_from_db()
    chunk.refresh_from_db()
    assert conversation.title == "ab"
    assert conversation.history_summary == "ab"
    assert conversation.ui_messages == [{"content": ["ab"]}]
    assert conversation.messages[0].parts[0].text == "ab"
    assert chunk.text == "ab"
