"""Unit tests for conversation with project LLM instructions."""

import json

import pytest
import respx
from freezegun import freeze_time
from rest_framework import status

from chat.factories import ChatConversationFactory, ChatProjectFactory, UserFactory
from chat.tests.utils import replace_uuids_with_placeholder

pytestmark = pytest.mark.django_db(transaction=True)

_HELLO_THERE_STREAM = (
    '0:"Hello"\n'
    '0:" there"\n'
    'f:{"messageId":"<mocked_uuid>"}\n'
    'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0,'
    '"co2Impact":0.0}}\n'
)


def _get_system_messages(last_respx_call):
    payload = json.loads(last_respx_call.request.content)
    return [m["content"] for m in payload["messages"] if m["role"] == "system"]


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Fixture to set AI service URLs for testing."""
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"

    return settings


@pytest.fixture(name="project_hello_data")
def project_hello_data_fixture():
    """Request payload with a simple Hello user message."""
    return {
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


@freeze_time("2025-07-25T10:36:35.297675Z")
@pytest.mark.parametrize(
    ("with_project", "expected_system_messages"),
    (
        [
            True,
            [
                "You are a helpful test assistant :)",
                "Today is Friday 25/07/2025.",
                "Answer in english.",
                "Always reply in bullet points.",
            ],
        ],
        [
            False,
            [
                "You are a helpful test assistant :)",
                "Today is Friday 25/07/2025.",
                "Answer in english.",
            ],
        ],
    ),
)
@respx.mock
def test_post_conversation_includes_project_llm_instructions(
    api_client, mock_openai_stream, project_hello_data, with_project, expected_system_messages
):
    """Test that project LLM instructions are sent to the LLM as part of the system prompt."""
    if with_project:
        project = ChatProjectFactory(
            owner=UserFactory(language="en-us"), llm_instructions="Always reply in bullet points."
        )
        conversation = ChatConversationFactory(owner=project.owner, project=project)
    else:
        conversation = ChatConversationFactory(owner__language="en-us")

    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data"
    api_client.force_login(conversation.owner)
    response = api_client.post(url, project_hello_data, format="json")

    assert response.status_code == status.HTTP_200_OK

    response_content = replace_uuids_with_placeholder(
        b"".join(response.streaming_content).decode("utf-8")
    )
    assert response_content == _HELLO_THERE_STREAM

    assert _get_system_messages(respx.calls.last) == expected_system_messages
    assert mock_openai_stream.called
