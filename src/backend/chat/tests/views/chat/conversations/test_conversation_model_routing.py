"""Persistence and sticky-model behavior for the post_conversation endpoint."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument

import json

from django.core.cache import cache as django_cache

import pytest
import respx
from freezegun import freeze_time
from rest_framework import status

from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.model_health import (
    model_health_cache_key,
    set_fallback_eviction_threshold,
    set_main_eviction_threshold,
)

pytestmark = pytest.mark.django_db(transaction=True)

FROZEN = "2025-07-25T10:36:35.297675Z"


@pytest.fixture(autouse=True)
def ai_settings(settings):
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"


@pytest.fixture(name="health_cache", autouse=True)
def health_cache_fixture():
    django_cache.clear()
    yield django_cache
    django_cache.clear()


def _make_llm(hrid: str, model_name: str) -> LLModel:
    return LLModel(
        hrid=hrid,
        model_name=model_name,
        human_readable_name=hrid,
        is_active=True,
        system_prompt="You are a helpful assistant.",
        tools=[],
        provider=LLMProvider(
            hrid=f"{hrid}-provider",
            base_url="https://www.external-ai-service.com/",
            api_key="test-api-key",
        ),
    )


@pytest.fixture(autouse=True)
def routed_llm_configs(settings):
    settings.LLM_CONFIGURATIONS = {
        "main-model": _make_llm("main-model", "main-llm"),
        "fallback-1": _make_llm("fallback-1", "fb1-llm"),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "main-model"
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = ""


@freeze_time(FROZEN)
@respx.mock
def test_new_conversation_pins_default_when_main_is_healthy(
    api_client, mock_openai_stream, hello_conversation_data
):
    conversation = ChatConversationFactory(owner__language="en-us")
    assert not conversation.model_hrid

    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    # drain the stream so the conversation is fully saved
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "main-model"


@freeze_time(FROZEN)
@respx.mock
def test_new_conversation_pins_fallback_when_main_is_red(
    api_client, mock_openai_stream, hello_conversation_data, health_cache
):
    health_cache.set(model_health_cache_key("main-model-provider", "main-llm"), "red")

    conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    # Main red, fb1 unknown (optimistic) -> pinned to fallback-1.
    assert conversation.model_hrid == "fallback-1"


@freeze_time(FROZEN)
@respx.mock
def test_existing_conversation_keeps_pinned_model_even_if_param_changes(
    api_client, mock_openai_stream, hello_conversation_data
):
    # Pre-pin the conversation to fallback-1: it must stay there even when the
    # request asks for "main-model" (or anything else).
    conversation = ChatConversationFactory(owner__language="en-us", model_hrid="fallback-1")

    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data&model_hrid=main-model"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "fallback-1"
    # And the actual outbound LLM call used the pinned model.
    assert json.loads(mock_openai_stream.calls.last.request.content)["model"] == "fb1-llm"


@freeze_time(FROZEN)
@respx.mock
def test_explicit_non_default_model_in_request_is_pinned(
    api_client, mock_openai_stream, hello_conversation_data
):
    # Picker selection in dev/staging: explicit non-default request goes through.
    conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data&model_hrid=fallback-1"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "fallback-1"


@freeze_time(FROZEN)
@respx.mock
def test_main_yellow_stays_on_main_under_default_threshold(
    api_client, mock_openai_stream, hello_conversation_data, health_cache
):
    # Default main threshold = "red": a slow main stays on main.
    health_cache.set(model_health_cache_key("main-model-provider", "main-llm"), "yellow")

    conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert (
        conversation.model_hrid == "main-model"
    )  # yellow is still "good enough" for the default threshold


@freeze_time(FROZEN)
@respx.mock
def test_main_yellow_stays_on_main_when_threshold_raised_to_red(
    api_client, mock_openai_stream, hello_conversation_data, health_cache
):
    # Admin raised the main threshold to "red": tolerate a slow main rather than
    # cascading to the fallback.
    set_main_eviction_threshold("red")
    health_cache.set(model_health_cache_key("main-model-provider", "main-llm"), "yellow")

    conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "main-model"


@freeze_time(FROZEN)
@respx.mock
def test_main_red_with_yellow_fb1_stays_on_fb1_under_default_fallback_threshold(
    api_client, mock_openai_stream, hello_conversation_data, health_cache, settings
):
    # Default fallback threshold = "red": a slow fb1 is tolerated, the flow stays on fb1.
    settings.LLM_CONFIGURATIONS = {
        **settings.LLM_CONFIGURATIONS,
        "fallback-2": _make_llm("fallback-2", "fb2-llm"),
    }
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"

    health_cache.set(model_health_cache_key("main-model-provider", "main-llm"), "red")
    health_cache.set(model_health_cache_key("fallback-1-provider", "fb1-llm"), "yellow")
    health_cache.set(model_health_cache_key("fallback-2-provider", "fb2-llm"), "green")

    conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "fallback-1"


@freeze_time(FROZEN)
@respx.mock
def test_fallback_threshold_red_accepts_yellow_fb1(
    api_client, mock_openai_stream, hello_conversation_data, health_cache
):
    # Admin set fallback threshold to "red": tolerate a slow fb1 rather than
    # skipping it (would otherwise fall through to the default).
    set_fallback_eviction_threshold("red")
    health_cache.set(model_health_cache_key("main-model-provider", "main-llm"), "red")
    health_cache.set(model_health_cache_key("fallback-1-provider", "fb1-llm"), "yellow")

    conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, hello_conversation_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)

    conversation.refresh_from_db()
    assert conversation.model_hrid == "fallback-1"
