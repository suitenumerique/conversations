"""Tests for chat admin classes."""

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache

import pytest

from chat.admin import ChatConversationAdmin, ModelHealthAdmin, RoutingTierSettingsForm
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel
from chat.model_health import model_health_cache_key
from chat.models import ChatConversation, ModelHealth, RoutingTierSettings

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


@pytest.fixture(name="tier_models")
def tier_models_fixture(settings):
    """Two chat models and a utility one."""
    defaults = {"is_active": True, "system_prompt": "hi", "tools": []}
    settings.LLM_CONFIGURATIONS = {
        "small": LLModel(
            hrid="small", model_name="test:small", human_readable_name="Small", **defaults
        ),
        "large": LLModel(
            hrid="large", model_name="test:large", human_readable_name="Large", **defaults
        ),
        "summarizer": LLModel(
            hrid="summarizer",
            model_name="test:summarizer",
            human_readable_name="Summarizer",
            role="utility",
            **defaults,
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "large"
    settings.LLM_TIER_SIMPLE_MODEL_HRID = ""


@pytest.mark.django_db
def test_routing_tier_settings_form_offers_chat_models_only(tier_models):  # pylint: disable=unused-argument
    """Tier dropdowns list chat models; the router may run on any configured model."""
    form = RoutingTierSettingsForm(instance=RoutingTierSettings.get_solo())

    assert form.fields["simple_model_hrid"].choices == [
        ("", "Use the setting (large)"),
        ("small", "Small (small)"),
        ("large", "Large (large)"),
    ]
    assert [value for value, _ in form.fields["simple_alternatives"].choices] == [
        "small",
        "large",
    ]
    assert "summarizer" in [value for value, _ in form.fields["router_model_hrid"].choices]


@pytest.mark.django_db
def test_routing_tier_settings_form_saves_alternatives_as_a_list(tier_models):  # pylint: disable=unused-argument
    """The multi-select is stored as a plain list of HRIDs in the JSON field."""
    form = RoutingTierSettingsForm(
        data={
            "simple_model_hrid": "small",
            "simple_alternatives": ["large"],
            "standard_model_hrid": "",
            "complex_model_hrid": "large",
            "router_model_hrid": "summarizer",
            "confidence_threshold": "0.8",
        },
        instance=RoutingTierSettings.get_solo(),
    )
    assert form.is_valid(), form.errors
    form.save()

    tier_settings = RoutingTierSettings.get_solo()
    assert tier_settings.simple_alternatives == ["large"]
    assert tier_settings.standard_alternatives == []
    assert tier_settings.model_for("standard") == "large"
    assert tier_settings.router_model_hrid == "summarizer"
    assert tier_settings.confidence_threshold == 0.8
