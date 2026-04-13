"""Unit tests for chat conversation actions in the with instruction concatenation"""

import json

import pytest
import respx
from freezegun import freeze_time

from chat.factories import ChatConversationFactory, ChatProjectFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.tests.utils import assert_data_stream_response

# enable database transactions for tests:
# transaction=True ensures that the data are available in the database
# in other threads
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def settings_with_concatenation(settings):
    """Fixture to set AI service URLs for testing."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="test-model",
            model_name="gpt-4",
            human_readable_name="Test Model",
            provider=LLMProvider(
                hrid="openai",
                kind="openai",
                base_url="https://www.external-ai-service.com/",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="base system prompt",
            tools=[],
            concatenate_instruction_messages=True,
        )
    }
    return settings


@freeze_time("2025-07-25T10:36:35.297675Z")
@pytest.mark.parametrize(
    ("conversation_in_project", "expected_system_message"),
    (
        [False, "base system prompt\n\nToday is Friday 25/07/2025.\n\nAnswer in english."],
        [
            True,
            (
                "base system prompt\n\nToday is Friday 25/07/2025.\n\nAnswer in english.\n\n"
                "Custom project instructions."
            ),
        ],
    ),
)
@respx.mock
def test_post_conversation_concatenate(
    api_client,
    hello_conversation_data,
    mock_openai_stream,
    conversation_in_project,
    expected_system_message,
):
    """The hook merges multiple SystemPromptParts into one before the model receives them."""
    if conversation_in_project:
        project = ChatProjectFactory(
            owner=UserFactory(language="en-us"), llm_instructions="Custom project instructions."
        )
        chat_conversation = ChatConversationFactory(owner=project.owner, project=project)
    else:
        chat_conversation = ChatConversationFactory(owner__language="en-us")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, hello_conversation_data, format="json")

    assert_data_stream_response(response)
    assert b"".join(response.streaming_content) is not None
    request_sent = mock_openai_stream.calls[0].request
    body = json.loads(request_sent.content)

    system_messages = [m for m in body["messages"] if m["role"] == "system"]
    assert len(system_messages) == 1
    assert system_messages[0]["content"] == expected_system_message
