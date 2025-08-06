"""Unit tests for chat conversation actions with web search RAG functionality."""
# pylint: disable=too-many-lines

import json

from django.utils import timezone

import httpx
import pytest
import respx
from freezegun import freeze_time
from rest_framework import status

from chat.ai_sdk_types import (
    LanguageModelV1Source,
    SourceUIPart,
    TextUIPart,
    UIMessage,
)
from chat.factories import ChatConversationFactory

# enable database transactions for tests:
# transaction=True ensures that the data are available in the database
# in other threads
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Fixture to set AI service URLs for testing."""
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"

    # Enable mocked web search backend for tests
    settings.RAG_WEB_SEARCH_BACKEND = "chat.agent_rag.web_search.mocked.MockedWebSearchManager"
    settings.RAG_WEB_SEARCH_PROMPT_UPDATE = (
        "Based on the following web search results:\n\n{search_results}\n\n"
        "Please answer the user's question: {user_prompt}"
    )

    # Set up AI routing model settings for intent detection
    settings.AI_ROUTING_MODEL = "mini-model"
    settings.AI_ROUTING_MODEL_BASE_URL = "https://www.mini-ai-service.com/"
    settings.AI_ROUTING_MODEL_API_KEY = "test-routing-api-key"
    settings.AI_ROUTING_SYSTEM_PROMPT = (
        "You are an intent detection model. Determine if the user's query requires a web search. "
        "Return true for web_search if the query asks about recent events, current news, "
        "or information that might not be in your training data."
    )

    return settings


@pytest.fixture(name="mock_openai_stream_with_web_search")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_stream_with_web_search():
    """
    Fixture to mock the OpenAI stream response for web search queries.
    """
    openai_stream = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {
                            "content": "Based on the web search results, I can tell you that"
                        },
                        "index": 0,
                        "finish_reason": None,
                    }
                ],
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
                        "delta": {
                            "content": " the James-Webb telescope has made significant discoveries."
                        },
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 25,
                    "total_tokens": 175,
                },
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_stream():
        for line in openai_stream.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        side_effect=[
            httpx.Response(200, stream=mock_stream()),
            # allow a second call for test_full_conversation_with_web_search
            httpx.Response(200, stream=mock_stream()),
        ]
    )

    return route


@pytest.fixture(name="mock_intent_detection_web_search")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_intent_detection_web_search():
    """
    Mock intent detection response that triggers web search.
    """
    intent_response = {
        "id": "chatcmpl-intent-123",
        "object": "chat.completion",
        "created": int(timezone.make_naive(timezone.now()).timestamp()),
        "model": "mini-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"web_search": true, "attachment_summary": false}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
    }

    route = respx.post("https://www.mini-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, json=intent_response)
    )

    return route


@pytest.fixture(name="mock_intent_detection_no_web_search")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_intent_detection_no_web_search():
    """
    Mock intent detection response that does not trigger web search.
    """
    intent_response = {
        "id": "chatcmpl-intent-456",
        "object": "chat.completion",
        "created": int(timezone.make_naive(timezone.now()).timestamp()),
        "model": "mini-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"web_search": false}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
    }

    route = respx.post("https://www.mini-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, json=intent_response)
    )

    return route


@pytest.fixture(name="history_conversation_with_web_search")
def history_conversation_with_web_search_fixture():
    """Create a conversation with existing message history for web search tests."""
    # Create a timestamp for the first message
    history_timestamp = timezone.now().replace(year=2025, month=6, day=15, hour=10, minute=30)

    # Create a conversation with pre-existing messages
    conversation = ChatConversationFactory()

    # Add previous user and assistant messages
    conversation.messages = [
        UIMessage(
            id="prev-user-msg-1",
            createdAt=history_timestamp,
            content="What is machine learning?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="What is machine learning?")],
        ),
        UIMessage(
            id="prev-assistant-msg-1",
            createdAt=history_timestamp.replace(minute=31),
            content=(
                "Machine learning is a branch of artificial intelligence "
                "that focuses on building systems that learn from data."
            ),
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[
                TextUIPart(
                    type="text",
                    text=(
                        "Machine learning is a branch of artificial intelligence "
                        "that focuses on building systems that learn from data."
                    ),
                )
            ],
        ),
    ]

    conversation.save()
    return conversation


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
@pytest.mark.parametrize(
    "force_web_search",
    [True, False],
)
def test_conversation_with_forced_web_search_no_history(
    api_client,
    mock_intent_detection_web_search,
    mock_openai_stream_with_web_search,
    mock_uuid4,
    force_web_search,
):
    """Test conversation with forced web search and no message history."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
    if force_web_search:
        url += "&force_web_search=true"

    data = {
        "messages": [
            {
                "id": "user-msg-1",
                "role": "user",
                "parts": [
                    {
                        "text": "What are the latest discoveries from James-Webb telescope?",
                        "type": "text",
                    }
                ],
                "content": "What are the latest discoveries from James-Webb telescope?",
                "createdAt": "2025-07-25T10:36:00.000Z",
            }
        ]
    }
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    assert response_content == (
        # source events starts with 'h:'
        'h:{"source_type": "url", "id": "cb2e1dd7-0f5b-4bed-9aec-93345ad9635b", '
        '"url": '
        '"https://www.lemonde.fr/sciences/article/2025/06/25/le-telescope-james-webb-decouvre-'
        'sa-premiere-exoplanete-identifiee-comme-une-petite-planete-froide_6615888_1650684.html", '
        '"title": null, "providerMetadata": {}}\n'
        'h:{"source_type": "url", "id": "cb2e1dd7-0f5b-4bed-9aec-93345ad9635b", '
        '"url": "https://www.franceinfo.fr/economie/budget/", "title": null, '
        '"providerMetadata": {}}\n'
        # Then the message text answer
        '0:"Based on the web search results, I can tell you that"\n'
        '0:" the James-Webb telescope has made significant discoveries."\n'
        'd:{"finishReason": "stop", "usage": {"promptTokens": 150, '
        '"completionTokens": 25}}\n'
    ).replace("cb2e1dd7-0f5b-4bed-9aec-93345ad9635b", str(mock_uuid4))

    # We should not have called intent detection if force_web_search is True
    assert mock_intent_detection_web_search.called is not force_web_search
    # The model stream should be called regardless of force_web_search
    assert mock_openai_stream_with_web_search.call_count == 1

    chat_conversation.refresh_from_db()

    # Check that UI messages were saved correctly
    assert chat_conversation.messages == [
        UIMessage(
            id=str(mock_uuid4),
            createdAt=timezone.now(),
            content="What are the latest discoveries from James-Webb telescope?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[
                TextUIPart(
                    type="text", text="What are the latest discoveries from James-Webb telescope?"
                )
            ],
        ),
        UIMessage(
            id=str(mock_uuid4),
            createdAt=timezone.now(),
            content=(
                "Based on the web search results, I can tell you that the James-Webb "
                "telescope has made significant discoveries."
            ),
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[
                TextUIPart(
                    type="text",
                    text=(
                        "Based on the web search results, I can tell you that the "
                        "James-Webb telescope has made significant discoveries."
                    ),
                ),
                SourceUIPart(
                    type="source",
                    source=LanguageModelV1Source(
                        source_type="url",
                        id=str(mock_uuid4),
                        url=(
                            "https://www.lemonde.fr/sciences/article/2025/06/25/le-telescope-james-"
                            "webb-decouvre-sa-premiere-exoplanete-identifiee-comme-une-petite-"
                            "planete-froide_6615888_1650684.html"
                        ),
                        title=None,
                        providerMetadata={},
                    ),
                ),
                SourceUIPart(
                    type="source",
                    source=LanguageModelV1Source(
                        source_type="url",
                        id=str(mock_uuid4),
                        url="https://www.franceinfo.fr/economie/budget/",
                        title=None,
                        providerMetadata={},
                    ),
                ),
            ],
        ),
    ]

    _user_request_parts = chat_conversation.pydantic_messages[0].pop("parts")
    assert len(_user_request_parts) == 2

    assert _user_request_parts[0] == {
        "content": "You are a helpful assistant. Escape formulas or any "
        "math notation between `$$`, like `$$x^2 + y^2 = "
        "z^2$$` or `$$C_l$$`. You can use Markdown to format "
        "your answers. ",
        "dynamic_ref": None,
        "part_kind": "system-prompt",
        "timestamp": "2025-07-25T10:36:35.297675Z",
    }

    _user_request_parts_1_content = _user_request_parts[1].pop("content")
    assert len(_user_request_parts_1_content) == 1
    # check the web result are properly prompted
    assert "Based on the following web search results:\n" in _user_request_parts_1_content[0]
    assert (
        "Please answer the user's question: What are the latest "
        "discoveries from James-Webb telescope?"
    ) in _user_request_parts_1_content[0]
    # check the web search results are included
    assert "le JWST a aidé à caractériser plusieurs" in _user_request_parts_1_content[0]

    assert _user_request_parts[1] == {
        "part_kind": "user-prompt",
        "timestamp": "2025-07-25T10:36:35.297675Z",
        # content as been tested above
    }
    assert chat_conversation.pydantic_messages[0] == {
        "instructions": None,
        "kind": "request",
        # parts are already checked above
    }

    assert chat_conversation.pydantic_messages[1] == {
        "kind": "response",
        "model_name": "test-model",
        "parts": [
            {
                "content": "Based on the web search results, I can tell you that "
                "the James-Webb telescope has made significant "
                "discoveries.",
                "part_kind": "text",
            }
        ],
        "timestamp": "2025-07-25T10:36:35.297675Z",
        "usage": {
            "details": None,
            "request_tokens": 150,
            "requests": 1,
            "response_tokens": 25,
            "total_tokens": 175,
        },
        "vendor_details": None,
        "vendor_id": None,
    }


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_conversation_with_intent_detected_web_search_no_history(
    api_client, mock_intent_detection_web_search, mock_openai_stream_with_web_search
):
    """Test conversation where web search is triggered by intent detection."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "user-msg-1",
                "role": "user",
                "parts": [
                    {"text": "What's the latest news about space exploration?", "type": "text"}
                ],
                "content": "What's the latest news about space exploration?",
                "createdAt": "2025-07-25T10:36:00.000Z",
            }
        ]
    }
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Check that web search sources are included
    lines = response_content.strip().split("\n")
    source_events = [line for line in lines if line.startswith("h:")]
    assert len(source_events) > 0, "Expected web search source events"

    # Both intent detection and main completion should be called
    assert mock_intent_detection_web_search.call_count == 1
    assert mock_openai_stream_with_web_search.call_count == 1


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_conversation_without_web_search_by_intent(
    api_client, mock_intent_detection_no_web_search, mock_openai_stream
):
    """Test conversation where web search is not triggered by intent detection."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "user-msg-1",
                "role": "user",
                "parts": [
                    {"text": "Explain the concept of recursion in programming", "type": "text"}
                ],
                "content": "Explain the concept of recursion in programming",
                "createdAt": "2025-07-25T10:36:00.000Z",
            }
        ]
    }
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Check that no web search sources are included
    assert response_content == (
        # The message text answer without web search sources (h: prefix)
        '0:"Hello"\n'
        '0:" there"\n'
        'd:{"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": '
        "0}}\n"
    )

    # Intent detection should be called, but not web search
    assert mock_intent_detection_no_web_search.call_count == 1
    assert mock_openai_stream.call_count == 1


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_conversation_with_web_search_and_history(
    api_client, history_conversation_with_web_search, mock_openai_stream_with_web_search
):
    """Test conversation with forced web search and existing message history."""
    conversation = history_conversation_with_web_search

    url = f"/api/v1.0/chats/{conversation.pk}/conversation/?protocol=data&force_web_search=true"
    data = {
        "messages": [
            {
                "id": "user-msg-2",
                "role": "user",
                "parts": [
                    {"text": "What are the recent breakthroughs in AI research?", "type": "text"}
                ],
                "content": "What are the recent breakthroughs in AI research?",
                "createdAt": "2025-07-25T10:36:00.000Z",
            }
        ]
    }
    api_client.force_login(conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Check that web search sources are included
    lines = response_content.strip().split("\n")
    source_events = [line for line in lines if line.startswith("h:")]
    assert len(source_events) > 0, "Expected web search source events"

    assert mock_openai_stream_with_web_search.call_count == 1

    conversation.refresh_from_db()

    # Check that we now have 4 messages (2 original + 2 new)
    assert len(conversation.messages) == 4

    # Check the new user message
    new_user_message = conversation.messages[2]
    assert new_user_message.role == "user"
    assert new_user_message.content == "What are the recent breakthroughs in AI research?"

    # Check the new assistant message with sources
    new_assistant_message = conversation.messages[3]
    assert new_assistant_message.role == "assistant"

    # Check that sources were added to the assistant message
    source_parts = [
        part
        for part in new_assistant_message.parts
        if hasattr(part, "type") and part.type == "source"
    ]
    assert len(source_parts) > 0, "Expected source parts in assistant message"


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_full_conversation_with_web_search(api_client, mock_openai_stream_with_web_search):
    """Test a full conversation with two user messages and web search."""
    chat_conversation = ChatConversationFactory()

    # First user message with forced web search
    url = (
        f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data&force_web_search=true"
    )
    data = {
        "messages": [
            {
                "id": "user-msg-1",
                "role": "user",
                "parts": [{"text": "What's new with the James-Webb telescope?", "type": "text"}],
                "content": "What's new with the James-Webb telescope?",
                "createdAt": "2025-07-25T10:36:00.000Z",
            }
        ]
    }
    api_client.force_login(chat_conversation.owner)

    response1 = api_client.post(url, data, format="json")
    assert response1.status_code == status.HTTP_200_OK

    # Consume the first response
    response1_content = b"".join(response1.streaming_content).decode("utf-8")
    lines1 = response1_content.strip().split("\n")
    source_events1 = [line for line in lines1 if line.startswith("h:")]
    assert len(source_events1) > 0, "Expected web search source events in first response"

    # Second user message with forced web search
    data = {
        "messages": [
            {
                "id": "user-msg-2",
                "role": "user",
                "parts": [
                    {"text": "Tell me more about exoplanets discovered recently", "type": "text"}
                ],
                "content": "Tell me more about exoplanets discovered recently",
                "createdAt": "2025-07-25T10:37:00.000Z",
            }
        ]
    }

    response2 = api_client.post(url, data, format="json")
    assert response2.status_code == status.HTTP_200_OK

    # Consume the second response
    response2_content = b"".join(response2.streaming_content).decode("utf-8")
    lines2 = response2_content.strip().split("\n")
    source_events2 = [line for line in lines2 if line.startswith("h:")]
    assert len(source_events2) > 0, "Expected web search source events in second response"

    assert mock_openai_stream_with_web_search.call_count == 2

    chat_conversation.refresh_from_db()

    # Check that we now have 4 messages total (2 user + 2 assistant)
    assert len(chat_conversation.messages) == 4

    # Verify the sequence of messages
    assert chat_conversation.messages[0].role == "user"
    assert chat_conversation.messages[0].content == "What's new with the James-Webb telescope?"

    assert chat_conversation.messages[1].role == "assistant"

    assert chat_conversation.messages[2].role == "user"
    assert (
        chat_conversation.messages[2].content == "Tell me more about exoplanets discovered recently"
    )

    assert chat_conversation.messages[3].role == "assistant"

    # Both assistant messages should have source parts
    for i in [1, 3]:
        assistant_message = chat_conversation.messages[i]
        source_parts = [
            part
            for part in assistant_message.parts
            if hasattr(part, "type") and part.type == "source"
        ]
        assert len(source_parts) > 0, f"Expected source parts in assistant message {i}"


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_conversation_with_web_search_text_protocol(api_client, mock_openai_stream_with_web_search):
    """Test conversation with web search using text protocol."""
    chat_conversation = ChatConversationFactory()

    url = (
        f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=text&force_web_search=true"
    )
    data = {
        "messages": [
            {
                "id": "user-msg-1",
                "role": "user",
                "parts": [{"text": "Latest space discoveries?", "type": "text"}],
                "content": "Latest space discoveries?",
                "createdAt": "2025-07-25T10:36:00.000Z",
            }
        ]
    }
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.streaming

    # For text protocol, we should get plain text response
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Text protocol should contain the actual response text
    assert response_content == (
        "Based on the web search results, I can tell you that the James-Webb "
        "telescope has made significant discoveries."
    )

    assert mock_openai_stream_with_web_search.call_count == 1

    chat_conversation.refresh_from_db()

    # Check that messages were saved correctly even with text protocol
    assert len(chat_conversation.messages) == 2

    # Check that sources were added to the assistant message
    assistant_message = chat_conversation.messages[1]
    source_parts = [
        part for part in assistant_message.parts if hasattr(part, "type") and part.type == "source"
    ]
    assert len(source_parts) > 0, "Expected source parts in assistant message"
