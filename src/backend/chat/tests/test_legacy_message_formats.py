"""Read surfaces against a database that holds both AI SDK message formats.

Conversations written before the v5 upgrade are never migrated: ``upconvert_v4_message``
brings them up to shape as they are parsed. The stored history therefore mixes both
shapes - across conversations, and inside a single one as soon as an old conversation is
continued. These tests plant genuine v4 rows with raw SQL: assigning them through the ORM
would upconvert them on the way in, leaving nothing legacy to read back.
"""

import json

from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test import RequestFactory

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.admin import ChatConversationAdmin
from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.factories import ChatConversationFactory
from chat.models import ChatConversation

pytestmark = pytest.mark.django_db

# A user turn as the v4 backend stored it: an attachment list beside the parts.
V4_USER_MESSAGE = {
    "id": "user-1",
    "role": "user",
    "content": "What is in this image?",
    "parts": [{"type": "text", "text": "What is in this image?"}],
    "experimental_attachments": [
        {"name": "sample.png", "contentType": "image/png", "url": "/media-key/sample.png"}
    ],
}

# An assistant turn as the v4 backend stored it: tool call, source and reasoning in
# their old shapes, and the CO2 impact carried as an annotation.
V4_ASSISTANT_MESSAGE = {
    "id": "trace-1",
    "role": "assistant",
    "content": "Here is what I found.",
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
        {"type": "source", "source": {"sourceType": "url", "id": "src-1", "url": "doc.pdf"}},
        {"type": "reasoning", "reasoning": "thinking out loud"},
    ],
}

# The next turn of that same conversation, written after the upgrade.
V5_ASSISTANT_MESSAGE = {
    "id": "trace-2",
    "role": "assistant",
    "metadata": {"co2_impact": 2.5e-9},
    "parts": [{"type": "text", "text": "And this is the follow-up."}],
}

UPCONVERTED_V4_USER_PARTS = [
    {"type": "text", "text": "What is in this image?"},
    {
        "type": "file",
        "mediaType": "image/png",
        "url": "/media-key/sample.png",
        "filename": "sample.png",
        "skipped": None,
    },
]

UPCONVERTED_V4_ASSISTANT_PARTS = [
    {"type": "step-start"},
    {
        "type": "tool-document_search_rag",
        "toolCallId": "call-1",
        "state": "output-available",
        "input": {"query": "what?"},
        "output": [{"url": "doc.pdf", "content": "..."}],
        "errorText": None,
    },
    {"type": "text", "text": "Here is what I found."},
    {"type": "source-url", "sourceId": "src-1", "url": "doc.pdf", "title": None},
    {"type": "reasoning", "text": "thinking out loud"},
]


def store_raw_messages(conversation, messages):
    """Write raw JSON straight into the column, bypassing the field's pydantic dump.

    Assigning ``conversation.messages`` would validate the list on the way out,
    which upconverts it - exactly what must not happen when planting a row that
    predates the upgrade.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {ChatConversation._meta.db_table} SET messages = %s WHERE id = %s",
            [json.dumps(messages), str(conversation.pk)],
        )


@pytest.fixture(name="text_only_model")
def text_only_model_fixture(settings):
    """Pin a model that cannot read images, so `images_skipped` inspects the history."""
    configurations = dict(settings.LLM_CONFIGURATIONS)
    hrid = "default-model"
    configurations[hrid] = configurations[hrid].model_copy(update={"supports_image": False})
    settings.LLM_CONFIGURATIONS = configurations
    return hrid


def test_retrieve_upconverts_a_conversation_mixing_both_formats(api_client):
    """The conversation GET view hands the client a v5 history, whatever is stored."""
    conversation = ChatConversationFactory()
    store_raw_messages(conversation, [V4_USER_MESSAGE, V4_ASSISTANT_MESSAGE, V5_ASSISTANT_MESSAGE])

    api_client.force_login(conversation.owner)
    response = api_client.get(f"/api/v1.0/chats/{conversation.pk}/")

    assert response.status_code == status.HTTP_200_OK
    messages = response.json()["messages"]
    assert [message["parts"] for message in messages] == [
        UPCONVERTED_V4_USER_PARTS,
        UPCONVERTED_V4_ASSISTANT_PARTS,
        V5_ASSISTANT_MESSAGE["parts"],
    ]
    # The v4 annotation became metadata; the v5 turn kept the metadata it was stored with.
    assert [message["metadata"] for message in messages] == [
        None,
        {"co2_impact": 1.5e-9},
        {"co2_impact": 2.5e-9},
    ]
    # Nothing v4-shaped reaches the client.
    assert not any("experimental_attachments" in message for message in messages)


def test_sidebar_lists_conversations_stored_in_both_formats(api_client):
    """The sidebar serializes every conversation's history, so one legacy row
    left unparsed would take the whole list down, not just its own entry."""
    owner = UserFactory()
    legacy = ChatConversationFactory(owner=owner)
    store_raw_messages(legacy, [V4_USER_MESSAGE, V4_ASSISTANT_MESSAGE])
    current = ChatConversationFactory(
        owner=owner,
        messages=[UIMessage(id="new-1", role="user", parts=[TextUIPart(type="text", text="hi")])],
    )

    api_client.force_login(owner)
    response = api_client.get("/api/v1.0/chats/?project=none")

    assert response.status_code == status.HTTP_200_OK
    histories = {result["id"]: result["messages"] for result in response.json()["results"]}
    assert [message["parts"] for message in histories[str(legacy.pk)]] == [
        UPCONVERTED_V4_USER_PARTS,
        UPCONVERTED_V4_ASSISTANT_PARTS,
    ]
    assert [message["parts"] for message in histories[str(current.pk)]] == [
        [{"type": "text", "text": "hi"}]
    ]


def test_sidebar_flags_images_skipped_on_a_v4_attachment(api_client, text_only_model):
    """`images_skipped` reads v5 file parts only: a legacy image has to be
    upconverted for the banner to still show on an old conversation."""
    conversation = ChatConversationFactory(model_hrid=text_only_model)
    store_raw_messages(conversation, [V4_USER_MESSAGE])

    api_client.force_login(conversation.owner)
    response = api_client.get("/api/v1.0/chats/?project=none")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["results"][0]["images_skipped"] is True


def test_admin_change_form_loads_a_conversation_mixing_both_formats():
    """The changelist defers `messages`; the change form is where the admin first
    parses them, one lazy query on the object it edits."""
    conversation = ChatConversationFactory()
    store_raw_messages(conversation, [V4_USER_MESSAGE, V4_ASSISTANT_MESSAGE, V5_ASSISTANT_MESSAGE])

    admin_instance = ChatConversationAdmin(ChatConversation, AdminSite())
    request = RequestFactory().get("/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    deferred = admin_instance.get_queryset(request).get(pk=conversation.pk)
    assert "messages" in deferred.get_deferred_fields()

    form = admin_instance.get_form(request, deferred)(instance=deferred)

    # Part shapes are asserted by the retrieve test; here what matters is that the
    # lazy load parses the legacy turns instead of raising on them.
    assert [[part.type for part in message.parts] for message in form.initial["messages"]] == [
        ["text", "file"],
        ["step-start", "tool-document_search_rag", "text", "source-url", "reasoning"],
        ["text"],
    ]
