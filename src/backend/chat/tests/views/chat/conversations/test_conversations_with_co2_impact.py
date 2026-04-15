"""Integration tests for CO2 impact data in the Albert provider."""

import json

from django.utils import timezone

import httpx
import pytest
import respx
from freezegun import freeze_time

from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db(transaction=True)

EXPECTED_CO2_IMPACT = 1e-05


@pytest.fixture(name="albert_settings", autouse=True)
def albert_settings_fixture(settings):
    """Configure Django settings to use the Albert LLM provider."""
    settings.LLM_DEFAULT_MODEL_HRID = "albert-model"
    settings.LLM_CONFIGURATIONS = {
        "albert-model": LLModel(
            hrid="albert-model",
            model_name="albert-large",
            human_readable_name="Albert Large",
            is_active=True,
            system_prompt="You are a helpful test assistant :)",
            tools=[],
            provider=LLMProvider(
                hrid="albert",
                kind="openai",
                base_url="https://www.external-ai-service.com/",
                api_key="test-api-key",
                co2_handling="albert",
            ),
        ),
    }
    return settings


@pytest.fixture(name="albert_conversation")
def albert_conversation_fixture(api_client):
    """Create an Albert-backed conversation and return (conversation, url)
    with the client logged in."""
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
    api_client.force_login(chat_conversation.owner)
    return chat_conversation, url


def _make_stream(with_co2: bool) -> str:
    """Build a minimal Albert-compatible SSE stream, optionally including CO2 data."""
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if with_co2:
        usage["impacts"] = {"kWh": 5.0e-6, "kgCO2eq": EXPECTED_CO2_IMPACT}

    return (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [{"delta": {"content": "Hello"}, "index": 0, "finish_reason": None}],
                "object": "chat.completion.chunk",
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": " there"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
                "usage": usage,
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_albert_co2_impact_appears_in_annotations_and_stream(
    api_client,
    mock_openai_stream_multi_calls,
    albert_conversation,
):
    """
    CO2 impact from Albert API is stored in messages[1].annotations in the database
    and accumulated in agent_usage across turns.
    """
    chat_conversation, url = albert_conversation
    data = {
        "messages": [
            {
                "id": "yuPoOuBkKA4FnKvk",
                "role": "user",
                "parts": [{"text": "Hello", "type": "text"}],
                "content": "Hello",
                "createdAt": "2025-07-03T15:22:17.105Z",
            }
        ]
    }

    response = api_client.post(url, data, format="json")
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content
    assert mock_openai_stream_multi_calls.called
    chat_conversation.refresh_from_db()

    # Verify the assistant message carries the CO2 annotation in the DB
    assert chat_conversation.messages[1].annotations == [
        {"co2_impact": pytest.approx(EXPECTED_CO2_IMPACT)}
    ]
    assert chat_conversation.agent_usage["co2_impact"] == pytest.approx(EXPECTED_CO2_IMPACT)

    # Add new User message to trigger another assistant response and verify
    # CO2 annotation appears again and is cumulative in agent_usage
    chat_conversation.refresh_from_db()
    second_data = {
        "messages": [
            data["messages"][0],
            {
                "id": chat_conversation.messages[1].id,
                "role": "assistant",
                "parts": [{"text": "Hello there", "type": "text"}],
                "content": "Hello there",
                "annotations": [{"co2_impact": EXPECTED_CO2_IMPACT}],
                "createdAt": "2025-07-25T10:36:35.297675Z",
            },
            {
                "id": "newMessageId12345",
                "role": "user",
                "parts": [{"text": "And again?", "type": "text"}],
                "content": "And again?",
                "createdAt": "2025-07-25T10:36:35.297675Z",
            },
        ]
    }

    second_response = api_client.post(url, second_data, format="json")

    second_response_content = b"".join(second_response.streaming_content).decode("utf-8")
    assert second_response_content
    # Verify CO2 annotation appears on the new assistant message
    chat_conversation.refresh_from_db()
    assert chat_conversation.messages[3].annotations == [
        {"co2_impact": pytest.approx(EXPECTED_CO2_IMPACT)}
    ]
    # agent_usage is the sum of each request usage
    assert chat_conversation.agent_usage["co2_impact"] == pytest.approx(2 * EXPECTED_CO2_IMPACT)


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_albert_co2_impact_preserved_when_second_request_has_no_co2(
    api_client,
    albert_conversation,
):
    """
    When a subsequent request returns no CO2 data (e.g. transient absence of
    the `impacts` field from Albert API), the previously accumulated co2_impact
    in agent_usage must not be discarded.
    """
    chat_conversation, url = albert_conversation
    call_count = 0

    def create_response(_request):
        nonlocal call_count
        call_count += 1  # add co2 only in first call
        stream_data = _make_stream(with_co2=call_count == 1)

        async def mock_stream():
            for line in stream_data.splitlines(keepends=True):
                yield line.encode()

        return httpx.Response(200, stream=mock_stream())

    respx.post("https://www.external-ai-service.com/chat/completions").mock(
        side_effect=create_response
    )

    # First request — Albert returns CO2 data
    first_data = {
        "messages": [
            {
                "id": "msg-1",
                "role": "user",
                "parts": [{"text": "Hello", "type": "text"}],
                "content": "Hello",
                "createdAt": "2025-07-25T10:36:35.297675Z",
            }
        ]
    }
    response = api_client.post(url, first_data, format="json")
    assert b"".join(response.streaming_content).decode("utf-8")
    chat_conversation.refresh_from_db()

    assert chat_conversation.messages[1].annotations == [
        {"co2_impact": pytest.approx(EXPECTED_CO2_IMPACT)}
    ]
    assert chat_conversation.agent_usage["co2_impact"] == pytest.approx(EXPECTED_CO2_IMPACT)

    # Second request — Albert returns NO CO2 data
    second_data = {
        "messages": [
            first_data["messages"][0],
            {
                "id": chat_conversation.messages[1].id,
                "role": "assistant",
                "parts": [{"text": "Hello there", "type": "text"}],
                "content": "Hello there",
                "annotations": [{"co2_impact": EXPECTED_CO2_IMPACT}],
                "createdAt": "2025-07-25T10:36:35.297675Z",
            },
            {
                "id": "msg-3",
                "role": "user",
                "parts": [{"text": "Again?", "type": "text"}],
                "content": "Again?",
                "createdAt": "2025-07-25T10:36:35.297675Z",
            },
        ]
    }
    second_response = api_client.post(url, second_data, format="json")
    assert b"".join(second_response.streaming_content).decode("utf-8")
    chat_conversation.refresh_from_db()

    # New assistant message should have no CO2 annotation (none returned by API)
    assert chat_conversation.messages[3].annotations in (None, [])
    # agent_usage must still carry the CO2 from the first request — not reset to zero
    assert chat_conversation.agent_usage["co2_impact"] == pytest.approx(EXPECTED_CO2_IMPACT)
