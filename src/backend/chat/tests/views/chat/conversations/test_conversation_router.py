"""Router wiring of the post_conversation endpoint."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument

import json
from unittest import mock

from django.core.cache import cache

import pytest
import respx
from freezegun import freeze_time
from rest_framework import status

from core.feature_flags.flags import FeatureFlags, FeatureToggle

from chat.enums import RoutingReason, RoutingTier, TierSource
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.models import RoutingTierSettings
from chat.router import RoutingLabels

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("clear_cache"),
]

FROZEN = "2025-07-25T10:36:35.297675Z"


def _make_llm(hrid: str, model_name: str, **overrides) -> LLModel:
    values = {
        "hrid": hrid,
        "model_name": model_name,
        "human_readable_name": hrid,
        "is_active": True,
        "system_prompt": "You are a helpful assistant.",
        "tools": [],
        "provider": LLMProvider(
            hrid=f"{hrid}-provider",
            base_url="https://www.external-ai-service.com/",
            api_key="test-api-key",
            co2_handling="albert",
        ),
    }
    values.update(overrides)
    return LLModel(**values)


@pytest.fixture(autouse=True)
def router_configs(settings):
    settings.LLM_CONFIGURATIONS = {
        "main-model": _make_llm("main-model", "main-llm"),
        "small-model": _make_llm("small-model", "small-llm"),
        "big-model": _make_llm("big-model", "big-llm"),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "main-model"
    settings.LLM_FALLBACK_MODEL_HRID_1 = ""
    settings.LLM_FALLBACK_MODEL_HRID_2 = ""
    settings.LLM_TIER_SIMPLE_MODEL_HRID = ""
    settings.LLM_TIER_STANDARD_MODEL_HRID = ""
    settings.LLM_TIER_COMPLEX_MODEL_HRID = ""
    tier_settings = RoutingTierSettings.get_solo()
    tier_settings.simple_model_hrid = "small-model"
    tier_settings.standard_model_hrid = "main-model"
    tier_settings.complex_model_hrid = "big-model"
    tier_settings.save()
    cache.clear()
    yield
    cache.clear()


def _flags(router: FeatureToggle) -> FeatureFlags:
    return FeatureFlags(
        web_search=FeatureToggle.ENABLED,
        document_upload=FeatureToggle.ENABLED,
        router=router,
    )


@pytest.fixture
def router_on(settings):
    settings.FEATURE_FLAGS = _flags(FeatureToggle.ENABLED)


@pytest.fixture
def router_off(settings):
    settings.FEATURE_FLAGS = _flags(FeatureToggle.DISABLED)


def _labels(complexity=RoutingTier.SIMPLE, confidence=0.95):
    return RoutingLabels(complexity=complexity, confidence=confidence)


def _classify_returning(labels):
    async def fake_classify(*_args, **_kwargs):
        return labels, RoutingReason.CLASSIFIED, 42

    return mock.patch("chat.router.routing.classify", side_effect=fake_classify)


def _post(api_client, conversation, data, query=""):
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/{query}"
    api_client.force_login(conversation.owner)
    return api_client.post(url, data, format="json")


def _drain(response) -> str:
    return b"".join(response.streaming_content).decode()


def _routing_parts(body: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ") and '"data-routing"' in line
    ]


# --- model picker ----------------------------------------------------------------------


@freeze_time(FROZEN)
@respx.mock
def test_unknown_model_hrid_is_rejected(
    api_client, mock_openai_stream, hello_conversation_data, router_on
):
    conversation = ChatConversationFactory(owner__language="en-us")
    response = _post(api_client, conversation, hello_conversation_data, "?model_hrid=ghost")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert mock_openai_stream.call_count == 0


@freeze_time(FROZEN)
@respx.mock
def test_requested_model_is_used_with_the_router_on(
    api_client, mock_openai_stream, hello_conversation_data, router_on
):
    conversation = ChatConversationFactory(owner__language="en-us")
    with mock.patch("chat.router.routing.classify") as classify:
        response = _post(api_client, conversation, hello_conversation_data, "?model_hrid=big-model")
    assert response.status_code == status.HTTP_200_OK
    _drain(response)
    classify.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.model_hrid == "big-model"
    assert json.loads(mock_openai_stream.calls.last.request.content)["model"] == "big-llm"


# --- tier query parameter --------------------------------------------------------------


@freeze_time(FROZEN)
@respx.mock
@pytest.mark.parametrize("tier", ["simple", "standard", "complex"])
def test_tier_param_pins_the_conversation(
    api_client, mock_openai_stream, hello_conversation_data, router_on, tier
):
    conversation = ChatConversationFactory(owner__language="en-us")
    with mock.patch("chat.router.routing.classify") as classify:
        response = _post(api_client, conversation, hello_conversation_data, f"?tier={tier}")
    assert response.status_code == status.HTTP_200_OK
    _drain(response)
    classify.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.pinned_tier == tier
    assert conversation.model_hrid == RoutingTierSettings.get_solo().model_for(tier)
    assert conversation.last_routing == {
        "tier": tier,
        "model_hrid": conversation.model_hrid,
        "labels": None,
    }
    metadata = conversation.messages[-1].metadata
    assert metadata["tier"] == tier
    assert metadata["tier_source"] == TierSource.USER.value
    assert metadata["router_reason"] == RoutingReason.USER_PINNED.value


@freeze_time(FROZEN)
@respx.mock
def test_pinned_tier_applies_to_the_next_turns(
    api_client, mock_openai_stream, hello_conversation_data, router_on
):
    conversation = ChatConversationFactory(owner__language="en-us", pinned_tier=RoutingTier.COMPLEX)
    with mock.patch("chat.router.routing.classify") as classify:
        response = _post(api_client, conversation, hello_conversation_data)
    _drain(response)
    classify.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.pinned_tier == "complex"
    assert conversation.model_hrid == "big-model"


@freeze_time(FROZEN)
@respx.mock
def test_tier_auto_clears_the_pin(
    api_client, mock_openai_stream, hello_conversation_data, router_on
):
    conversation = ChatConversationFactory(owner__language="en-us", pinned_tier=RoutingTier.COMPLEX)
    with _classify_returning(_labels(RoutingTier.SIMPLE, 0.95)):
        response = _post(api_client, conversation, hello_conversation_data, "?tier=auto")
    assert response.status_code == status.HTTP_200_OK
    _drain(response)
    conversation.refresh_from_db()
    assert conversation.pinned_tier is None
    assert conversation.model_hrid == "small-model"


@freeze_time(FROZEN)
@respx.mock
def test_invalid_tier_is_rejected(
    api_client, mock_openai_stream, hello_conversation_data, router_on
):
    conversation = ChatConversationFactory(owner__language="en-us")
    response = _post(api_client, conversation, hello_conversation_data, "?tier=turbo")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --- routing per turn ------------------------------------------------------------------


@freeze_time(FROZEN)
@respx.mock
def test_router_on_resolves_the_model_per_turn_and_streams_the_decision(
    api_client, mock_openai_stream, hello_conversation_data, router_on
):
    # Previously on the main model; this turn is classified simple.
    conversation = ChatConversationFactory(owner__language="en-us", model_hrid="main-model")
    with _classify_returning(_labels(RoutingTier.SIMPLE, 0.95)):
        response = _post(api_client, conversation, hello_conversation_data)
    assert response.status_code == status.HTTP_200_OK
    body = _drain(response)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "small-model"
    assert conversation.last_routing == {
        "tier": "simple",
        "model_hrid": "small-model",
        "labels": {"complexity": "simple", "confidence": 0.95},
    }
    assert json.loads(mock_openai_stream.calls.last.request.content)["model"] == "small-llm"

    assert _routing_parts(body) == [
        {
            "type": "data-routing",
            "data": {
                "type": "routing",
                "tier": "simple",
                "tier_label": "router.tier.simple",
                "tier_source": "router",
                "changed": True,
            },
            "transient": True,
        }
    ]

    assistant = conversation.messages[-1]
    assert assistant.role == "assistant"
    assert assistant.metadata["tier"] == "simple"
    assert assistant.metadata["tier_source"] == "router"
    assert assistant.metadata["router_reason"] == "classified"
    assert assistant.metadata["router_confidence"] == 0.95
    assert assistant.metadata["router_latency_ms"] == 42


@freeze_time(FROZEN)
@respx.mock
def test_router_off_keeps_upstream_behaviour(
    api_client, mock_openai_stream, hello_conversation_data, router_off
):
    """With the flag off the router never runs and a tier parameter is ignored."""
    conversation = ChatConversationFactory(owner__language="en-us", model_hrid="main-model")
    with mock.patch("chat.router.routing.route_turn") as route_turn:
        response = _post(api_client, conversation, hello_conversation_data, "?tier=simple")
    assert response.status_code == status.HTTP_200_OK
    body = _drain(response)
    route_turn.assert_not_called()
    assert "data-routing" not in body

    conversation.refresh_from_db()
    assert conversation.model_hrid == "main-model"
    assert conversation.pinned_tier is None
    assert conversation.last_routing == {}
    assert "tier" not in (conversation.messages[-1].metadata or {})
