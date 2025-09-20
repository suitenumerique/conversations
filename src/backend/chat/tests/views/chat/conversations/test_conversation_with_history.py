"""Unit tests for chat conversation actions with existing message history."""
# pylint: disable=too-many-lines

import json

from django.utils import timezone

import pytest
import respx
from freezegun import freeze_time
from rest_framework import status

from chat.ai_sdk_types import (
    Attachment,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
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

    # Disable web search backend for tests
    settings.RAG_WEB_SEARCH_BACKEND = None

    return settings


@pytest.fixture(name="history_conversation")
def history_conversation_fixture():
    """Create a conversation with existing message history."""
    # Create a timestamp for the first message
    history_timestamp = timezone.now().replace(year=2025, month=6, day=15, hour=10, minute=30)

    # Create a conversation with pre-existing messages
    conversation = ChatConversationFactory()

    # Add previous user and assistant messages
    conversation.messages = [
        UIMessage(
            id="prev-user-msg-1",
            createdAt=history_timestamp,
            content="How does machine learning work?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="How does machine learning work?")],
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
        UIMessage(
            id="prev-user-msg-2",
            createdAt=history_timestamp.replace(minute=32),
            content="What are neural networks?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="What are neural networks?")],
        ),
        UIMessage(
            id="prev-assistant-msg-2",
            createdAt=history_timestamp.replace(minute=33),
            content=(
                "Neural networks are computing systems inspired by the "
                "biological neural networks in animal brains."
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
                        "Neural networks are computing systems inspired by the "
                        "biological neural networks in animal brains."
                    ),
                )
            ],
        ),
    ]

    # Set up the OpenAI message format as well
    conversation.pydantic_messages = [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful assistant. Escape formulas or any "
                    "math notation between `$$`, like `$$x^2 + y^2 = "
                    "z^2$$` or `$$C_l$$`. You can use Markdown to format "
                    "your answers. ",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-06-15T10:30:00.000000Z",
                },
                {
                    "content": ["How does machine learning work?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-06-15T10:30:00.000000Z",
                },
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "content": (
                        "Machine learning is a branch of artificial intelligence that "
                        "focuses on building systems that learn from data."
                    ),
                    "part_kind": "text",
                }
            ],
            "timestamp": "2025-06-15T10:31:00.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 10,
                "requests": 1,
                "response_tokens": 20,
                "total_tokens": 30,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": ["What are neural networks?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-06-15T10:32:00.000000Z",
                },
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "content": (
                        "Neural networks are computing systems inspired by the "
                        "biological neural networks in animal brains."
                    ),
                    "part_kind": "text",
                }
            ],
            "timestamp": "2025-06-15T10:33:00.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 5,
                "requests": 1,
                "response_tokens": 15,
                "total_tokens": 20,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
    ]

    conversation.save()
    return conversation


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_data_protocol_with_history(
    api_client, mock_openai_stream, mock_uuid4, history_conversation
):
    """Test posting messages to a conversation with history using the 'data' protocol."""
    url = f"/api/v1.0/chats/{history_conversation.pk}/conversation/?protocol=data"
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
    api_client.force_login(history_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    assert mock_openai_stream.called

    # Verify that the request to OpenAI included the conversation history
    request_sent = mock_openai_stream.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history is included in the messages sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + at least 3 more messages from history

    # Verify the conversation still has its history plus the new messages
    history_conversation.refresh_from_db()
    # The UI messages should only include the most recent one (sent from frontend)
    assert history_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    # But the history should now have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation.messages) == 6

    # Verify the most recent message is the new one
    assert history_conversation.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert history_conversation.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    # Verify that the pydantic_messages were appended correctly
    assert len(history_conversation.pydantic_messages) == 6  # Original 4 + 2 new ones


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_text_protocol_with_history(
    api_client, mock_openai_stream, mock_uuid4, history_conversation
):
    """Test posting messages to a conversation with history using the 'text' protocol."""
    url = f"/api/v1.0/chats/{history_conversation.pk}/conversation/?protocol=text"
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
    api_client.force_login(history_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.streaming

    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == "Hello there"

    assert mock_openai_stream.called

    # Verify the conversation still has its history plus the new messages
    history_conversation.refresh_from_db()
    # The UI messages should only include the most recent one (sent from frontend)
    assert history_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    # But the messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation.messages) == 6

    # Verify the most recent messages are the new ones
    assert history_conversation.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert history_conversation.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_with_image_with_history(
    api_client, mock_openai_stream_image, mock_uuid4, history_conversation
):
    """
    Ensure an image URL is correctly forwarded to the AI service with a conversation with history.
    """
    url = f"/api/v1.0/chats/{history_conversation.pk}/conversation/?protocol=data"

    data = {
        "messages": [
            {
                "id": "7x3hLsq6rB3xp91T",
                "role": "user",
                "parts": [{"text": "Hello, what do you see on this picture?", "type": "text"}],
                "content": "Hello, what do you see on this picture?",
                "createdAt": "2025-07-07T15:52:27.822Z",
                "experimental_attachments": [
                    {
                        "url": (
                            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAA"
                            "ABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5C"
                            "YII="
                        ),
                        "name": "FELV-cat.jpg",
                        "contentType": "image/png",
                    }
                ],
            }
        ]
    }
    api_client.force_login(history_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        '0:"I see a cat"\n'
        '0:" in the picture."\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # --- Verify the outgoing HTTP request body contains the image ---
    request_sent = mock_openai_stream_image.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history is included in the messages sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + at least 3 more messages from history

    # Check the image is in the most recent message
    assert "content" in body["messages"][-1]
    assert isinstance(body["messages"][-1]["content"], list)
    assert len(body["messages"][-1]["content"]) == 2
    assert body["messages"][-1]["content"][0]["text"] == "Hello, what do you see on this picture?"
    assert "image_url" in body["messages"][-1]["content"][1]

    # Verify the conversation still has its history plus the new messages
    history_conversation.refresh_from_db()
    # The UI messages should only include the most recent one (sent from frontend)
    assert history_conversation.ui_messages == [
        {
            "content": "Hello, what do you see on this picture?",
            "createdAt": "2025-07-07T15:52:27.822Z",
            "experimental_attachments": [
                {
                    "contentType": "image/png",
                    "name": "FELV-cat.jpg",
                    "url": (
                        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAA"
                        "ABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5C"
                        "YII="
                    ),
                }
            ],
            "id": "7x3hLsq6rB3xp91T",
            "parts": [{"text": "Hello, what do you see on this picture?", "type": "text"}],
            "role": "user",
        }
    ]

    # But the messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation.messages) == 6

    # Verify the most recent message has the image attachment
    assert history_conversation.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello, what do you see on this picture?",
        reasoning=None,
        experimental_attachments=[
            Attachment(
                name=None,
                contentType="image/png",
                url=(
                    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+w"
                    "SzIAAAABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEA"
                    "AAAASUVORK5CYII="
                ),
            )
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello, what do you see on this picture?")],
    )

    assert history_conversation.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="I see a cat in the picture.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="I see a cat in the picture.")],
    )


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_tool_call_with_history(
    api_client, mock_openai_stream_tool, mock_uuid4, settings, history_conversation
):
    """
    Ensure tool calls are correctly forwarded and streamed back with a conversation with history.
    """
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    url = f"/api/v1.0/chats/{history_conversation.pk}/conversation/?protocol=data"

    data = {
        "messages": [
            {
                "id": "tool-msg-1",
                "role": "user",
                "parts": [{"type": "text", "text": "Weather in Paris?"}],
                "content": "Weather in Paris?",
                "createdAt": "2025-07-18T12:00:00Z",
            }
        ]
    }
    api_client.force_login(history_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        'b:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","toolName":'
        '"get_current_weather"}\n'
        'c:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","argsTextDelta":'
        '"{\\"location\\":\\"Paris\\", \\"unit\\":\\"celsius\\"}"}\n'
        'a:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","result":{"location":'
        '"Paris","temperature":22,"unit":"celsius"}}\n'
        '0:"The current weather in Paris is nice"\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # --- Verify the outgoing HTTP request body ---
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history is included in the messages sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + at least 3 more messages from history

    # Check the most recent message contains the weather question
    assert "content" in body["messages"][-1]
    assert isinstance(body["messages"][-1]["content"], list)
    assert body["messages"][-1]["content"][0]["text"] == "Weather in Paris?"

    history_conversation.refresh_from_db()
    # The UI messages should only include the most recent one (sent from frontend)
    assert history_conversation.ui_messages == [
        {
            "content": "Weather in Paris?",
            "createdAt": "2025-07-18T12:00:00Z",
            "id": "tool-msg-1",
            "parts": [{"text": "Weather in Paris?", "type": "text"}],
            "role": "user",
        }
    ]

    # But the messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation.messages) == 6

    # Verify the most recent message is the new one with tool invocation
    assert history_conversation.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Weather in Paris?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Weather in Paris?")],
    )

    assert history_conversation.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="The current weather in Paris is nice",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    toolCallId="xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                    toolName="get_current_weather",
                    args={"unit": "celsius", "location": "Paris"},
                    state="call",
                    step=None,
                ),
            ),
            TextUIPart(type="text", text="The current weather in Paris is nice"),
        ],
    )

    # Verify that the pydantic_messages were appended correctly
    assert (
        len(history_conversation.pydantic_messages) == 8
    )  # Original 4 + 4 new ones (2 tool requests)


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_tool_call_fails_with_history(
    api_client, mock_openai_stream_tool, mock_uuid4, settings, history_conversation
):
    """
    Ensure tool calls are correctly forwarded and streamed back when failing with a
    conversation with history.
    """
    settings.AI_AGENT_TOOLS = []

    url = f"/api/v1.0/chats/{history_conversation.pk}/conversation/?protocol=data"

    data = {
        "messages": [
            {
                "id": "tool-msg-1",
                "role": "user",
                "parts": [{"type": "text", "text": "Weather in Paris?"}],
                "content": "Weather in Paris?",
                "createdAt": "2025-07-18T12:00:00Z",
            }
        ]
    }
    api_client.force_login(history_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        'b:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","toolName":'
        '"get_current_weather"}\n'
        'c:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","argsTextDelta":'
        '"{\\"location\\":\\"Paris\\", \\"unit\\":\\"celsius\\"}"}\n'
        'a:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","result":"Unknown tool '
        "name: 'get_current_weather'. No tools available.\"}\n"
        '0:"I cannot give you an answer to that."\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # --- Verify the outgoing HTTP request body ---
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history is included in the messages sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + at least 3 more messages from history

    # Check the most recent message contains the weather question
    assert "content" in body["messages"][-1]
    assert isinstance(body["messages"][-1]["content"], list)
    assert body["messages"][-1]["content"][0]["text"] == "Weather in Paris?"

    history_conversation.refresh_from_db()
    # The UI messages should only include the most recent one (sent from frontend)
    assert history_conversation.ui_messages == [
        {
            "content": "Weather in Paris?",
            "createdAt": "2025-07-18T12:00:00Z",
            "id": "tool-msg-1",
            "parts": [{"text": "Weather in Paris?", "type": "text"}],
            "role": "user",
        }
    ]

    # But the messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation.messages) == 6

    # Verify the most recent message is the new one with tool invocation
    assert history_conversation.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Weather in Paris?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Weather in Paris?")],
    )

    assert history_conversation.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="I cannot give you an answer to that.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    toolCallId="xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                    toolName="get_current_weather",
                    args={"unit": "celsius", "location": "Paris"},
                    state="call",
                    step=None,
                ),
            ),
            TextUIPart(type="text", text="I cannot give you an answer to that."),
        ],
    )

    # Verify that the pydantic_messages were appended correctly
    assert (
        len(history_conversation.pydantic_messages) == 8
    )  # Original 4 + 4 new ones (2 tool requests)


@pytest.fixture(name="history_conversation_with_image")
def history_conversation_with_image_fixture():
    """Create a conversation with existing message history that includes an image."""
    # Create a timestamp for the first message
    history_timestamp = timezone.now().replace(year=2025, month=6, day=15, hour=10, minute=30)

    # Create a conversation with pre-existing messages including an image
    conversation = ChatConversationFactory()

    # Add previous user and assistant messages with an image
    conversation.messages = [
        UIMessage(
            id="prev-user-msg-1",
            createdAt=history_timestamp,
            content="Hello, what do you see in this image?",
            reasoning=None,
            experimental_attachments=[
                Attachment(
                    name="test-image.jpg",
                    contentType="image/png",
                    url=(
                        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAA"
                        "ABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5C"
                        "YII="
                    ),
                )
            ],
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="Hello, what do you see in this image?")],
        ),
        UIMessage(
            id="prev-assistant-msg-1",
            createdAt=history_timestamp.replace(minute=31),
            content="I see a small black square in the image.",
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="I see a small black square in the image.")],
        ),
        UIMessage(
            id="prev-user-msg-2",
            createdAt=history_timestamp.replace(minute=32),
            content="Can you tell me more about it?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="Can you tell me more about it?")],
        ),
        UIMessage(
            id="prev-assistant-msg-2",
            createdAt=history_timestamp.replace(minute=33),
            content=(
                "It appears to be a very simple image with a small black square "
                "in the center on a white background."
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
                        "It appears to be a very simple image with a small black square in "
                        "the center on a white background."
                    ),
                )
            ],
        ),
    ]

    # Set up the OpenAI message format as well
    conversation.pydantic_messages = [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful assistant. Escape formulas or any "
                    "math notation between `$$`, like `$$x^2 + y^2 = "
                    "z^2$$` or `$$C_l$$`. You can use Markdown to format "
                    "your answers. ",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-06-15T10:30:00.000000Z",
                },
                {
                    "content": [
                        "Hello, what do you see in this image?",
                        {
                            "data": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD-wSzIAAAABlBMVEX___-_"
                                "v7-jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD_aNpbtEAAAAASUVORK5CYII="
                            ),
                            "kind": "binary",
                            "identifier": "plop",
                            "media_type": "image/png",
                            "vendor_metadata": None,
                        },
                    ],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-06-15T10:30:00.000000Z",
                },
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "I see a small black square in the image.", "part_kind": "text"}],
            "timestamp": "2025-06-15T10:31:00.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 15,
                "requests": 1,
                "response_tokens": 10,
                "total_tokens": 25,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": ["Can you tell me more about it?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-06-15T10:32:00.000000Z",
                },
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "content": (
                        "It appears to be a very simple image with a small black "
                        "square in the center on a white background."
                    ),
                    "part_kind": "text",
                }
            ],
            "timestamp": "2025-06-15T10:33:00.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 8,
                "requests": 1,
                "response_tokens": 20,
                "total_tokens": 28,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
    ]

    conversation.save()
    return conversation


@pytest.fixture(name="history_conversation_with_tool")
def history_conversation_with_tool_fixture():
    """Create a conversation with existing message history that includes a tool invocation."""
    # Create a timestamp for the first message
    history_timestamp = timezone.now().replace(year=2025, month=6, day=15, hour=10, minute=30)

    # Create a conversation with pre-existing messages including a tool invocation
    conversation = ChatConversationFactory()

    # Add previous user and assistant messages with tool invocation
    conversation.messages = [
        UIMessage(
            id="prev-user-msg-1",
            createdAt=history_timestamp,
            content="What's the weather like in London?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="What's the weather like in London?")],
        ),
        UIMessage(
            id="prev-assistant-msg-1",
            createdAt=history_timestamp.replace(minute=31),
            content="The current weather in London is cloudy with a temperature of 18°C.",
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[
                ToolInvocationUIPart(
                    type="tool-invocation",
                    toolInvocation=ToolInvocationCall(
                        toolCallId="previous-tool-call-123",
                        toolName="get_current_weather",
                        args={"location": "London", "unit": "celsius"},
                        state="call",
                        step=None,
                    ),
                ),
                TextUIPart(
                    type="text",
                    text="The current weather in London is cloudy with a temperature of 18°C.",
                ),
            ],
        ),
        UIMessage(
            id="prev-user-msg-2",
            createdAt=history_timestamp.replace(minute=32),
            content="And how about tomorrow?",
            reasoning=None,
            experimental_attachments=None,
            role="user",
            annotations=None,
            toolInvocations=None,
            parts=[TextUIPart(type="text", text="And how about tomorrow?")],
        ),
        UIMessage(
            id="prev-assistant-msg-2",
            createdAt=history_timestamp.replace(minute=33),
            content=(
                "Tomorrow's forecast for London shows partly sunny conditions with a high of 20°C."
            ),
            reasoning=None,
            experimental_attachments=None,
            role="assistant",
            annotations=None,
            toolInvocations=None,
            parts=[
                ToolInvocationUIPart(
                    type="tool-invocation",
                    toolInvocation=ToolInvocationCall(
                        toolCallId="previous-tool-call-456",
                        toolName="get_current_weather",
                        args={"location": "London", "days": 1, "unit": "celsius"},
                        state="call",
                        step=None,
                    ),
                ),
                TextUIPart(
                    type="text",
                    text=(
                        "Tomorrow's forecast for London shows partly "
                        "sunny conditions with a high of 20°C."
                    ),
                ),
            ],
        ),
    ]

    # Set up the OpenAI message format as well
    conversation.pydantic_messages = [
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": "You are a helpful assistant. Escape formulas or any "
                    "math notation between `$$`, like `$$x^2 + y^2 = "
                    "z^2$$` or `$$C_l$$`. You can use Markdown to format "
                    "your answers. ",
                    "dynamic_ref": None,
                    "part_kind": "system-prompt",
                    "timestamp": "2025-06-15T10:30:00.000000Z",
                },
                {
                    "content": ["What's the weather like in London?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-06-15T10:30:00.000000Z",
                },
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "args": '{"location":"London", "unit":"celsius"}',
                    "part_kind": "tool-call",
                    "tool_call_id": "previous-tool-call-123",
                    "tool_name": "get_current_weather",
                }
            ],
            "timestamp": "2025-06-15T10:31:00.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 12,
                "requests": 1,
                "response_tokens": 8,
                "total_tokens": 20,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": {
                        "location": "London",
                        "temperature": 18,
                        "unit": "celsius",
                        "condition": "cloudy",
                    },
                    "metadata": None,
                    "part_kind": "tool-return",
                    "timestamp": "2025-06-15T10:31:15.000000Z",
                    "tool_call_id": "previous-tool-call-123",
                    "tool_name": "get_current_weather",
                }
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "content": (
                        "The current weather in London is cloudy with a temperature of 18°C."
                    ),
                    "part_kind": "text",
                }
            ],
            "timestamp": "2025-06-15T10:31:30.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 15,
                "requests": 1,
                "response_tokens": 12,
                "total_tokens": 27,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": ["And how about tomorrow?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-06-15T10:32:00.000000Z",
                },
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "args": '{"location":"London", "days":1, "unit":"celsius"}',
                    "part_kind": "tool-call",
                    "tool_call_id": "previous-tool-call-456",
                    "tool_name": "get_current_weather",
                }
            ],
            "timestamp": "2025-06-15T10:32:30.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 5,
                "requests": 1,
                "response_tokens": 10,
                "total_tokens": 15,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
        {
            "instructions": None,
            "kind": "request",
            "parts": [
                {
                    "content": {
                        "location": "London",
                        "forecast": [
                            {
                                "day": 1,
                                "temperature": 20,
                                "unit": "celsius",
                                "condition": "partly sunny",
                            }
                        ],
                    },
                    "metadata": None,
                    "part_kind": "tool-return",
                    "timestamp": "2025-06-15T10:32:45.000000Z",
                    "tool_call_id": "previous-tool-call-456",
                    "tool_name": "get_current_weather",
                }
            ],
        },
        {
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "content": (
                        "Tomorrow's forecast for London shows partly sunny "
                        "conditions with a high of 20°C."
                    ),
                    "part_kind": "text",
                }
            ],
            "timestamp": "2025-06-15T10:33:00.000000Z",
            "usage": {
                "details": None,
                "request_tokens": 18,
                "requests": 1,
                "response_tokens": 14,
                "total_tokens": 32,
            },
            "vendor_details": None,
            "vendor_id": None,
        },
    ]

    conversation.save()
    return conversation


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_with_existing_image_history(
    api_client, mock_openai_stream, mock_uuid4, history_conversation_with_image
):
    """Test posting a message to a conversation that already has images in its history."""
    url = f"/api/v1.0/chats/{history_conversation_with_image.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "yuPoOuBkKA4FnKvk",
                "role": "user",
                "parts": [{"text": "What was in that image again?", "type": "text"}],
                "content": "What was in that image again?",
                "createdAt": "2025-07-03T15:22:17.105Z",
            }
        ]
    }
    api_client.force_login(history_conversation_with_image.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    assert mock_openai_stream.called

    # Verify that the request to OpenAI included the conversation history with the image
    request_sent = mock_openai_stream.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history including the image is sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + history messages

    # The first user message in history should contain an image
    image_found = False
    for message in body["messages"]:
        if message["role"] == "user" and isinstance(message.get("content"), list):
            for content_part in message["content"]:
                if isinstance(content_part, dict) and content_part.get("type") == "image_url":
                    image_found = True
                    break

    assert image_found, "The image from the conversation history was not forwarded to OpenAI"

    # Verify the conversation still has its original history plus the new messages
    history_conversation_with_image.refresh_from_db()

    # The messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation_with_image.messages) == 6

    # Verify the most recent messages are the new ones
    assert history_conversation_with_image.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="What was in that image again?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="What was in that image again?")],
    )

    assert history_conversation_with_image.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    # Verify that the pydantic_messages were appended correctly
    assert len(history_conversation_with_image.pydantic_messages) == 6  # Original 4 + 2 new ones


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_with_existing_tool_history(
    api_client, mock_openai_stream_tool, mock_uuid4, settings, history_conversation_with_tool
):
    """Test posting a message to a conversation that already has tool calls in its history."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    url = f"/api/v1.0/chats/{history_conversation_with_tool.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "tool-history-msg-1",
                "role": "user",
                "parts": [{"type": "text", "text": "How about Paris weather?"}],
                "content": "How about Paris weather?",
                "createdAt": "2025-07-18T12:00:00Z",
            }
        ]
    }
    api_client.force_login(history_conversation_with_tool.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        'b:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","toolName":'
        '"get_current_weather"}\n'
        'c:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","argsTextDelta":'
        '"{\\"location\\":\\"Paris\\", \\"unit\\":\\"celsius\\"}"}\n'
        'a:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","result":{"location":'
        '"Paris","temperature":22,"unit":"celsius"}}\n'
        '0:"The current weather in Paris is nice"\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    assert mock_openai_stream_tool.called

    # Verify that the request to OpenAI included the conversation history with tool calls
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history including tool calls is sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + history messages

    # Verify the conversation still has its original history plus the new messages
    history_conversation_with_tool.refresh_from_db()

    # The messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation_with_tool.messages) == 6

    # Verify the most recent message is the new one with tool invocation
    assert history_conversation_with_tool.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="How about Paris weather?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="How about Paris weather?")],
    )

    assert history_conversation_with_tool.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="The current weather in Paris is nice",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    toolCallId="xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                    toolName="get_current_weather",
                    args={"unit": "celsius", "location": "Paris"},
                    state="call",
                    step=None,
                ),
            ),
            TextUIPart(type="text", text="The current weather in Paris is nice"),
        ],
    )

    # The pydantic_messages should include both the original tool calls and the new ones
    assert len(history_conversation_with_tool.pydantic_messages) == 12  # Original 8 + 4 new ones

    # Verify the new tool call request is included
    assert history_conversation_with_tool.pydantic_messages[8] == {
        "instructions": None,
        "kind": "request",
        "parts": [
            {
                "content": ["How about Paris weather?"],
                "part_kind": "user-prompt",
                "timestamp": "2025-07-25T10:36:35.297675Z",
            }
        ],
    }

    assert history_conversation_with_tool.pydantic_messages[9] == {
        "finish_reason": "tool_call",
        "kind": "response",
        "model_name": "test-model",
        "parts": [
            {
                "args": '{"location":"Paris", "unit":"celsius"}',
                "part_kind": "tool-call",
                "tool_call_id": "xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                "tool_name": "get_current_weather",
            }
        ],
        "provider_details": {"finish_reason": "tool_calls"},
        "provider_name": "openai",
        "provider_response_id": "chatcmpl-tool-call",
        "timestamp": "2025-07-25T10:36:35.297675Z",
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 0,
            "output_audio_tokens": 0,
            "output_tokens": 0,
        },
    }

    assert history_conversation_with_tool.pydantic_messages[10] == {
        "instructions": None,
        "kind": "request",
        "parts": [
            {
                "content": {"location": "Paris", "temperature": 22, "unit": "celsius"},
                "metadata": None,
                "part_kind": "tool-return",
                "timestamp": "2025-07-25T10:36:35.297675Z",
                "tool_call_id": "xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                "tool_name": "get_current_weather",
            }
        ],
    }

    assert history_conversation_with_tool.pydantic_messages[11] == {
        "finish_reason": "stop",
        "kind": "response",
        "model_name": "test-model",
        "parts": [
            {"content": "The current weather in Paris is nice", "id": None, "part_kind": "text"}
        ],
        "provider_details": {"finish_reason": "stop"},
        "provider_name": "openai",
        "provider_response_id": "chatcmpl-final",
        "timestamp": "2025-07-25T10:36:35.297675Z",
        "usage": {
            "cache_audio_read_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
            "input_audio_tokens": 0,
            "input_tokens": 0,
            "output_audio_tokens": 0,
            "output_tokens": 0,
        },
    }


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_add_image_to_conversation_with_tool_history(
    api_client, mock_openai_stream_image, mock_uuid4, history_conversation_with_tool
):
    """Test adding an image to a conversation that already has tool calls in its history."""
    url = f"/api/v1.0/chats/{history_conversation_with_tool.pk}/conversation/?protocol=data"

    data = {
        "messages": [
            {
                "id": "7x3hLsq6rB3xp91T",
                "role": "user",
                "parts": [{"text": "How's the weather in this image?", "type": "text"}],
                "content": "How's the weather in this image?",
                "createdAt": "2025-07-07T15:52:27.822Z",
                "experimental_attachments": [
                    {
                        "url": (
                            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAA"
                            "ABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5C"
                            "YII="
                        ),
                        "name": "weather.jpg",
                        "contentType": "image/png",
                    }
                ],
            }
        ]
    }
    api_client.force_login(history_conversation_with_tool.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == (
        '0:"I see a cat"\n'
        '0:" in the picture."\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # Verify that the request to OpenAI included both
    # the conversation history with tool calls and the new image
    request_sent = mock_openai_stream_image.calls[0].request
    body = json.loads(request_sent.content)

    # Check that the history is sent to OpenAI
    assert len(body["messages"]) >= 4  # System prompt + history messages

    # Check the most recent message contains the image
    assert "content" in body["messages"][-1]
    assert isinstance(body["messages"][-1]["content"], list)
    assert len(body["messages"][-1]["content"]) == 2
    assert body["messages"][-1]["content"][0]["text"] == "How's the weather in this image?"
    assert "image_url" in body["messages"][-1]["content"][1]

    # Verify the conversation has its history plus the new messages
    history_conversation_with_tool.refresh_from_db()

    # The messages field should have 6 messages - 4 from history + 2 new ones
    assert len(history_conversation_with_tool.messages) == 6

    # Verify the most recent message has the image attachment
    assert history_conversation_with_tool.messages[4] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="How's the weather in this image?",
        reasoning=None,
        experimental_attachments=[
            Attachment(
                name=None,
                contentType="image/png",
                url=(
                    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+w"
                    "SzIAAAABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEA"
                    "AAAASUVORK5CYII="
                ),
            )
        ],
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="How's the weather in this image?")],
    )

    assert history_conversation_with_tool.messages[5] == UIMessage(
        id=str(mock_uuid4),  # Mocked UUID
        createdAt=timezone.now(),  # Mocked timestamp
        content="I see a cat in the picture.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="I see a cat in the picture.")],
    )
