"""Tests for chat admin classes."""

from uuid import uuid4

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory

import pytest

from core.factories import UserFactory

from chat.admin import ChatConversationAdmin, ChatStreamChunkInline, ModelHealthAdmin
from chat.factories import ChatConversationFactory
from chat.model_health import model_health_cache_key
from chat.models import ChatConversation, ChatStreamChunk, ModelHealth

# Big enough for the stored size to stand out from a short conversation's.
HEAVY_HISTORY = [{"role": "user", "content": f"message number {i} " * 40} for i in range(5000)]


@pytest.mark.django_db
def test_model_health_admin_save_updates_cache(clear_cache):  # pylint: disable=unused-argument
    """Editing a status in the admin mirrors the new value into the Redis cache."""
    key = model_health_cache_key("albert", "some-model")
    obj = ModelHealth.objects.create(provider="albert", model_id="some-model", status="green")
    cache.set(key, "green", timeout=None)

    obj.status = "red"
    admin_instance = ModelHealthAdmin(ModelHealth, AdminSite())
    admin_instance.save_model(request=None, obj=obj, form=None, change=True)

    assert ModelHealth.objects.get(pk=obj.pk).status == "red"
    assert cache.get(key) == "red"


@pytest.mark.django_db
def test_conversation_admin_changelist_ranks_by_stored_size():
    """The changelist sizes each conversation from the columns it does not select."""
    light = ChatConversationFactory(pydantic_messages=[{"content": "hi"}])
    heavy = ChatConversationFactory(pydantic_messages=HEAVY_HISTORY)

    queryset = ChatConversationAdmin(ChatConversation, AdminSite()).get_queryset(request=None)
    sizes = {conversation.pk: conversation.stored_size for conversation in queryset}

    assert sizes[heavy.pk] > sizes[light.pk] > 0
    assert list(queryset.order_by("-stored_size").values_list("pk", flat=True)) == [
        heavy.pk,
        light.pk,
    ]


@pytest.mark.django_db
def test_conversation_admin_lists_the_chunks_of_a_pending_turn():
    """The inline names each kind of row without loading what the row carries."""
    conversation = ChatConversationFactory()
    run_id = uuid4()
    for seq, fields in enumerate(
        [
            {"parts": [{"kind": "request"}, {"kind": "response"}]},
            {"text": "a" * 120},
            {},
        ]
    ):
        ChatStreamChunk.objects.create(conversation=conversation, run_id=run_id, seq=seq, **fields)

    # The inline checks the viewer's permissions, so unlike the changelist above
    # it needs a request to answer with.
    request = RequestFactory().get("/")
    request.user = UserFactory(is_staff=True, is_superuser=True)

    inline = ChatStreamChunkInline(ChatConversation, AdminSite())
    # Scoped to this conversation: the inline queryset spans the whole table, since
    # the change page is what narrows it to the object being displayed.
    chunks = list(inline.get_queryset(request).filter(conversation=conversation))

    assert [inline.content(chunk) for chunk in chunks] == [
        "snapshot of 2 message(s)",
        "120 characters of text",
        "keepalive beat",
    ]
    # The point of the annotations: the sizes come back without the payloads.
    assert chunks[0].get_deferred_fields() == {"parts", "text"}
