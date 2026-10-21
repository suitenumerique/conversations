"""Tests for NUL characters in conversation JSON fields, which Postgres jsonb rejects."""

import pytest

from chat import models
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


def test_json_fields_nul_characters_are_stripped():
    """NUL characters in nested values and keys are stripped, even when `save` is bypassed."""
    conversation = ChatConversationFactory()
    models.ChatConversation.objects.filter(pk=conversation.pk).update(
        ui_messages=[{"content\x00": ["a\x00b"]}],
        messages=[
            UIMessage(id="msg-1", role="assistant", parts=[TextUIPart(type="text", text="a\x00b")])
        ],
    )

    conversation.refresh_from_db()
    assert conversation.ui_messages == [{"content": ["ab"]}]
    assert conversation.messages[0].parts[0].text == "ab"
