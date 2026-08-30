"""Tests for chat admin classes."""

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache

import pytest

from chat.admin import ChatConversationAdmin, ModelHealthAdmin
from chat.factories import ChatConversationFactory
from chat.model_health import model_health_cache_key
from chat.models import ChatConversation, ModelHealth

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
