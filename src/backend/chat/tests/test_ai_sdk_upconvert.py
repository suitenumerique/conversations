"""Tests for the v4 -> v5 upconversion of stored (and inbound) messages.

Conversations written before the SDK v5 upgrade are never migrated in the
database: they are brought up to shape when parsed. These fixtures mirror what
the v4 backend actually stored.
"""

import pytest

from chat.ai_sdk_types import DEFAULT_MEDIA_TYPE, UIMessage, upconvert_v4_message
from chat.clients.pydantic_ui_message_converter import ui_message_to_user_content

# An assistant turn as `_prepare_update_conversation` stored it under v4.
V4_ASSISTANT_MESSAGE = {
    "id": "trace-1234",
    "role": "assistant",
    "content": "Here is what I found.",
    "createdAt": "2026-07-25T10:36:35.297675Z",
    "annotations": [{"co2_impact": 1.5e-9}],
    "parts": [
        {"type": "step-start"},
        {
            "type": "tool-invocation",
            "toolInvocation": {
                "state": "result",
                "toolCallId": "call-1",
                "toolName": "document_search_rag",
                "args": {"query": "what?"},
                "result": [{"url": "doc.pdf", "content": "..."}],
            },
        },
        {"type": "text", "text": "Here is what I found."},
        {
            "type": "source",
            "source": {
                "sourceType": "url",
                "id": "src-1",
                "url": "doc.pdf",
                "title": None,
                "providerMetadata": {},
            },
        },
        {
            "type": "reasoning",
            "reasoning": "thinking out loud",
            "details": [{"type": "text", "text": "thinking out loud", "signature": "sig"}],
        },
    ],
}

# A user turn with an image the model could not read.
V4_USER_MESSAGE = {
    "id": "user-1",
    "role": "user",
    "content": "What is in this image?",
    "parts": [{"type": "text", "text": "What is in this image?"}],
    "experimental_attachments": [
        {
            "name": "sample.png",
            "contentType": "image/png",
            "url": "/media-key/sample.png",
            "skipped": {"reason": "model_text_only"},
        }
    ],
}


def test_upconverts_a_stored_assistant_message():
    """Every v4 part shape becomes its v5 equivalent."""
    message = UIMessage.model_validate(V4_ASSISTANT_MESSAGE)

    assert message.metadata == {"co2_impact": 1.5e-9}
    assert [part.model_dump(exclude_none=True) for part in message.parts] == [
        {"type": "step-start"},
        {
            "type": "tool-document_search_rag",
            "toolCallId": "call-1",
            "state": "output-available",
            "input": {"query": "what?"},
            "output": [{"url": "doc.pdf", "content": "..."}],
        },
        {"type": "text", "text": "Here is what I found."},
        {"type": "source-url", "sourceId": "src-1", "url": "doc.pdf"},
        {"type": "reasoning", "text": "thinking out loud"},
    ]


def test_upconverts_attachments_to_file_parts():
    """Attachments move onto the parts, keeping the `skipped` stamp the UI reads."""
    message = UIMessage.model_validate(V4_USER_MESSAGE)

    assert [part.model_dump(exclude_none=True) for part in message.parts] == [
        {"type": "text", "text": "What is in this image?"},
        {
            "type": "file",
            "mediaType": "image/png",
            "url": "/media-key/sample.png",
            "filename": "sample.png",
            "skipped": {"reason": "model_text_only"},
        },
    ]


def test_upconverts_an_attachment_stored_without_a_content_type():
    """`contentType` was optional in v4; a missing one must not fail the read."""
    message = UIMessage.model_validate(
        {
            "id": "user-2",
            "role": "user",
            "parts": [],
            "experimental_attachments": [{"url": "/media-key/unknown.bin"}],
        }
    )

    assert [part.model_dump(exclude_none=True) for part in message.parts] == [
        {"type": "file", "mediaType": DEFAULT_MEDIA_TYPE, "url": "/media-key/unknown.bin"}
    ]


def test_synthesizes_a_text_part_from_a_bare_content():
    """The oldest messages have no parts at all, only the deprecated `content`."""
    message = UIMessage.model_validate(
        {"id": "old-1", "role": "user", "content": "Hello", "parts": []}
    )

    assert [part.model_dump(exclude_none=True) for part in message.parts] == [
        {"type": "text", "text": "Hello"}
    ]


@pytest.mark.parametrize("raw", [V4_ASSISTANT_MESSAGE, V4_USER_MESSAGE], ids=["assistant", "user"])
def test_upconversion_is_idempotent(raw):
    """A v5 message passes through untouched, so re-parsing is safe."""
    once = UIMessage.model_validate(raw)
    twice = UIMessage.model_validate(once.model_dump(exclude_none=True))

    assert twice.model_dump() == once.model_dump()
    assert upconvert_v4_message(once.model_dump(exclude_none=True)) == once.model_dump(
        exclude_none=True
    )


def test_llm_history_is_unchanged_by_the_upconversion():
    """The content handed to the model is the same before and after the shim."""
    upconverted = UIMessage.model_validate(upconvert_v4_message(dict(V4_USER_MESSAGE)))

    assert ui_message_to_user_content(UIMessage.model_validate(V4_USER_MESSAGE)) == (
        ui_message_to_user_content(upconverted)
    )
