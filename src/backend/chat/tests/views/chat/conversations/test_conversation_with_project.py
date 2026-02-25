"""Unit tests for conversation with project LLM instructions."""

import json

import pytest
import respx
from freezegun import freeze_time
from rest_framework import status

from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.tests.utils import replace_uuids_with_placeholder

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Fixture to set AI service URLs for testing."""
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"

    return settings


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_includes_project_llm_instructions(api_client, mock_openai_stream):
    """Test that project LLM instructions are sent to the LLM as part of the system prompt."""
    project = ChatProjectFactory(llm_instructions="Always reply in bullet points.")
    conversation = ChatConversationFactory(
        owner=project.owner, project=project, owner__language="en-us"
    )

    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "msg-1",
                "role": "user",
                "parts": [{"text": "Hello", "type": "text"}],
                "content": "Hello",
                "createdAt": "2025-07-03T15:22:17.105Z",
            }
        ]
    }
    api_client.force_login(conversation.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    response_content = replace_uuids_with_placeholder(response_content)
    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    last_request_payload = json.loads(respx.calls.last.request.content)
    system_message = last_request_payload["messages"][0]
    assert system_message["role"] == "system"
    assert "Always reply in bullet points." in system_message["content"]
    assert mock_openai_stream.called


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_without_project_has_no_project_instructions(
    api_client, mock_openai_stream
):
    """Test that conversations without a project do not include project instructions."""
    conversation = ChatConversationFactory(owner__language="en-us")

    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "msg-1",
                "role": "user",
                "parts": [{"text": "Hello", "type": "text"}],
                "content": "Hello",
                "createdAt": "2025-07-03T15:22:17.105Z",
            }
        ]
    }
    api_client.force_login(conversation.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    last_request_payload = json.loads(respx.calls.last.request.content)
    system_message = last_request_payload["messages"][0]
    assert system_message["role"] == "system"
    assert system_message["content"] == (
        "You are a helpful test assistant :)\n\nToday is Friday 25/07/2025.\n\nAnswer in english."
    )
    assert mock_openai_stream.called
