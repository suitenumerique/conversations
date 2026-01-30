"""Unit tests for chat conversation actions in the chat API view."""
# pylint: disable=too-many-lines

import json
import logging
from unittest.mock import ANY, patch

from django.utils import timezone

import pytest
import respx
from asgiref.sync import sync_to_async
from dirty_equals import IsUUID
from freezegun import freeze_time
from rest_framework import status

from core.factories import UserFactory

from chat.ai_sdk_types import (
    Attachment,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.tests.utils import replace_uuids_with_placeholder

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
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"

    return settings


def test_post_conversation_anonymous(api_client):
    """Test posting messages as an anonymous user returns a 401 error."""
    chat_conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/"
    data = {"messages": [{"role": "user", "content": "Hello there"}]}
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_post_conversation_other_user(api_client):
    """Test posting messages to another user's conversation returns a 404 error."""
    chat_conversation = ChatConversationFactory()
    other_user = UserFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/"
    data = {"messages": [{"role": "user", "content": "Hello there"}]}
    api_client.force_login(other_user)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_post_conversation_no_messages(api_client):
    """Test posting with no messages returns a 400 error."""
    chat_conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/"
    data = {"messages": []}
    api_client.force_login(chat_conversation.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_post_conversation_invalid_protocol(api_client):
    """Test posting with an invalid protocol returns a 400 error."""
    chat_conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=invalid"
    data = {"messages": [{"role": "user", "content": "Hello there"}]}
    api_client.force_login(chat_conversation.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"protocol": ["Protocol must be either 'text' or 'data'."]}


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_data_protocol(api_client, mock_openai_stream):
    """Test posting messages to a conversation using the 'data' protocol."""
    chat_conversation = ChatConversationFactory(owner__language="en-us")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    assert mock_openai_stream.called

    # ensure instructions are merged as a system prompt
    last_request_payload = json.loads(respx.calls.last.request.content)
    assert last_request_payload["messages"][0] == {
        "content": (
            "You are a helpful test assistant :)\n\nToday is Friday 25/07/2025.\n\n"
            "Answer in english."
        ),
        "role": "system",
    }

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]

    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Hello"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "Hello there", "id": None, "part_kind": "text"}],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-1234567890",
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
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
@patch("chat.keepalive.get_current_time")
def test_post_conversation_data_protocol_triggers_keepalives(
    mock_time, api_client, mock_openai_stream
):
    """Test streaming response contains keepalive messages"""
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    mock_time.side_effect = [float(i * 60) for i in range(10)]
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
        '2:[{"status": "WAITING"}]\n'
    )

    assert mock_openai_stream.called

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\n"
                "Answer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Hello"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "Hello there", "id": None, "part_kind": "text"}],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-1234567890",
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
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_text_protocol(api_client, mock_openai_stream):
    """Test posting messages to a conversation using the 'text' protocol."""
    chat_conversation = ChatConversationFactory(owner__language="en-us")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=text"
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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.streaming

    response_content = b"".join(response.streaming_content).decode("utf-8")
    assert response_content == "Hello there"

    assert mock_openai_stream.called
    # ensure instructions are merged as a system prompt
    last_request_payload = json.loads(respx.calls.last.request.content)
    assert last_request_payload["messages"][0] == {
        "content": (
            "You are a helpful test assistant :)\n\nToday is Friday 25/07/2025.\n\n"
            "Answer in english."
        ),
        "role": "system",
    }

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]

    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Hello"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "Hello there", "id": None, "part_kind": "text"}],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-1234567890",
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
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_with_image(api_client, mock_openai_stream_image):
    """Ensure an image URL is correctly forwarded to the AI service."""
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"

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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"I see a cat"\n'
        '0:" in the picture."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # --- Verify the outgoing HTTP request body contains the image ---
    request_sent = mock_openai_stream_image.calls[0].request
    body = json.loads(request_sent.content)

    # Check the exact structure expected by the AI service
    assert body["messages"] == [
        {
            "content": (
                "You are a helpful test assistant :)\n\nToday is Friday 25/07/2025."
                "\n\nAnswer in english."
            ),
            "role": "system",
        },
        {
            "content": [
                {"text": "Hello, what do you see on this picture?", "type": "text"},
                {
                    "image_url": {
                        # "detail": "auto",
                        "url": (
                            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAA"
                            "ABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5C"
                            "YII="
                        ),
                    },
                    "type": "image_url",
                },
            ],
            "role": "user",
        },
    ]
    assert body["model"] == "test-model"
    assert body["stream"] is True

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
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

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
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

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="I see a cat in the picture.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="I see a cat in the picture.")],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": [
                        "Hello, what do you see on this picture?",
                        {
                            "data": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD-wSzIAAAABlBMVEX___-_"
                                "v7-jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD_aNpbtEAAAAASUVORK5CYII="
                            ),
                            "kind": "binary",
                            "identifier": "FELV-cat.jpg",
                            "media_type": "image/png",
                            "vendor_metadata": None,
                        },
                    ],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "I see a cat in the picture.", "id": None, "part_kind": "text"}],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-1234567890",
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
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_tool_call(api_client, mock_openai_stream_tool, settings):
    """Ensure tool calls are correctly forwarded and streamed back."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    chat_conversation = ChatConversationFactory(owner__language="en-us")
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"

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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        'b:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","toolName":'
        '"get_current_weather"}\n'
        'c:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","argsTextDelta":'
        '"{\\"location\\":\\"Paris\\", \\"unit\\":\\"celsius\\"}"}\n'
        'a:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","result":{"location":'
        '"Paris","temperature":22,"unit":"celsius"}}\n'
        '0:"The current weather in Paris is nice"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # --- Verify the outgoing HTTP request body ---
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    assert body["messages"] == [
        {
            "content": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "role": "system",
        },
        {"content": [{"text": "Weather in Paris?", "type": "text"}], "role": "user"},
    ]

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Weather in Paris?",
            "createdAt": "2025-07-18T12:00:00Z",
            "id": "tool-msg-1",
            "parts": [{"text": "Weather in Paris?", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Weather in Paris?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Weather in Paris?")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
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

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Weather in Paris?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "tool_call",
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "args": '{"location":"Paris", "unit":"celsius"}',
                    "id": None,
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
            "run_id": _run_id,
        },
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
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
            "run_id": _run_id,
        },
        {
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
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_tool_call_fails(api_client, mock_openai_stream_tool, settings):
    """Ensure tool calls are correctly forwarded and streamed back when failing."""
    settings.AI_AGENT_TOOLS = []

    chat_conversation = ChatConversationFactory(owner__language="fr-fr")
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"

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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        'b:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","toolName":"get_current_weather"}\n'
        'c:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","argsTextDelta":'
        '"{\\"location\\":\\"Paris\\", \\"unit\\":\\"celsius\\"}"}\n'
        'a:{"toolCallId":"xLDcIljdsDrz0idal7tATWSMm2jhMj47","result":"Unknown tool '
        "name: 'get_current_weather'. No tools available.\"}\n"
        '0:"I cannot give you an answer to that."\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # --- Verify the outgoing HTTP request body ---
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    assert body["messages"] == [
        {
            "content": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in french."
            ),
            "role": "system",
        },
        {"content": [{"text": "Weather in Paris?", "type": "text"}], "role": "user"},
    ]

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Weather in Paris?",
            "createdAt": "2025-07-18T12:00:00Z",
            "id": "tool-msg-1",
            "parts": [{"text": "Weather in Paris?", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Weather in Paris?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Weather in Paris?")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
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

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in french."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Weather in Paris?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "tool_call",
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {
                    "args": '{"location":"Paris", "unit":"celsius"}',
                    "id": None,
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
            "run_id": _run_id,
        },
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in french."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": "Unknown tool name: 'get_current_weather'. No tools available.",
                    "part_kind": "retry-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                    "tool_call_id": "xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                    "tool_name": "get_current_weather",
                }
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [
                {"content": "I cannot give you an answer to that.", "id": None, "part_kind": "text"}
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
            "run_id": _run_id,
        },
    ]


def test_post_conversation_model_selection_invalid(api_client):
    """Test the user cannot select a different model if it does not exist."""
    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data&model_hrid=plop"
    data = {
        "messages": [
            {
                "id": "yuPoOuBkKA4FnKvk",
                "role": "user",
                "parts": [{"text": "Hello", "type": "text"}],
                "content": "Hello",
                "createdAt": "2025-07-03T15:22:17.105Z",
            }
        ],
    }
    api_client.force_login(chat_conversation.owner)
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    assert response.json() == {"model_hrid": ["Invalid model_hrid."]}


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
def test_post_conversation_model_selection_new(
    api_client,
    mock_openai_stream,
    settings,
):
    """Test the user can select a different model."""
    settings.LLM_CONFIGURATIONS = {
        "plop": LLModel(
            hrid="plop",
            model_name="plop-model",
            human_readable_name="Plop Model",
            is_active=True,
            system_prompt="You are a helpful assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="external-ai-service",
                base_url="https://www.external-ai-service.com/",
                api_key="test-api-key",
            ),
        ),
    }

    chat_conversation = ChatConversationFactory()

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data&model_hrid=plop"
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
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the streaming content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    # We check the model used in the outgoing request to the AI service
    assert json.loads(mock_openai_stream.calls.last.request.content)["model"] == "plop-model"


@freeze_time("2025-07-25T10:36:35.297675Z")
@pytest.mark.parametrize("stream_delay", [None, 0.0001])
@respx.mock
def test_post_conversation_data_protocol_no_stream(
    api_client,
    mock_openai_no_stream,
    settings,
    stream_delay,
):
    """
    Test posting messages to a conversation using the 'data' protocol without streaming.
    """
    settings.FAKE_STREAMING_DELAY = stream_delay
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="model-1",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="unused",
                base_url="https://www.external-ai-service.com",
                api_key="key",
            ),
            supports_streaming=False,
        ),
    }

    chat_conversation = ChatConversationFactory(owner__language="en-us")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
    data = {
        "messages": [
            {
                "id": "yuPoOuBkKA4FnKvk",
                "role": "user",
                "parts": [{"text": "Why the sky is blue?", "type": "text"}],
                "content": "Why the sky is blue?",
                "createdAt": "2025-07-03T15:22:17.105Z",
            }
        ]
    }
    api_client.force_login(chat_conversation.owner)

    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    # Wait for the content to be fully received
    response_content = b"".join(response.streaming_content).decode("utf-8")

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    if stream_delay:
        assert response_content == (
            '0:"The "\n'
            '0:"sky "\n'
            '0:"appe"\n'
            '0:"ars "\n'
            '0:"blue"\n'
            '0:" due"\n'
            '0:" to "\n'
            '0:"a ph"\n'
            '0:"enom"\n'
            '0:"enon"\n'
            '0:" cal"\n'
            '0:"led "\n'
            '0:"Rayl"\n'
            '0:"eigh"\n'
            '0:" sca"\n'
            '0:"tter"\n'
            '0:"ing."\n'
            'f:{"messageId":"<mocked_uuid>"}\n'
            'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":135}}\n'
        )
    else:
        assert response_content == (
            '0:"The sky appears blue due to a phenomenon called Rayleigh scattering."\n'
            'f:{"messageId":"<mocked_uuid>"}\n'
            'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":135}}\n'
        )

    assert mock_openai_no_stream.called

    chat_conversation.refresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Why the sky is blue?",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Why the sky is blue?", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,
        createdAt=timezone.now(),  # Mocked timestamp
        content="Why the sky is blue?",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Why the sky is blue?")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="The sky appears blue due to a phenomenon called Rayleigh scattering.",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[
            TextUIPart(
                type="text",
                text="The sky appears blue due to a phenomenon called Rayleigh scattering.",
            )
        ],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are an amazing assistant.\n\nToday is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Why the sky is blue?"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
            "parts": [
                {
                    "content": "The sky appears blue due to a phenomenon called "
                    "Rayleigh scattering.",
                    "id": None,
                    "part_kind": "text",
                }
            ],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-92c413bb5a45426299335d0621324654",
            "timestamp": "2025-09-22T14:13:49Z",
            "usage": {
                "cache_audio_read_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "details": {},
                "input_audio_tokens": 0,
                "input_tokens": 0,
                "output_audio_tokens": 0,
                "output_tokens": 135,
            },
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z")
@respx.mock
@pytest.mark.asyncio
async def test_post_conversation_async(api_client, mock_openai_stream, monkeypatch, caplog):
    """Test posting messages to a conversation using the 'data' protocol."""
    monkeypatch.setenv("PYTHON_SERVER_MODE", "async")

    chat_conversation = await sync_to_async(ChatConversationFactory)(owner__language="en-us")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
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
    await api_client.aforce_login(chat_conversation.owner)

    caplog.clear()
    caplog.set_level(level=logging.DEBUG, logger="chat.views")

    response = await sync_to_async(api_client.post)(url, data, format="json")  # client is sync

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    assert "Using ASYNC streaming for chat conversation" in caplog.text

    # Wait for the streaming content to be fully received => async iterator -> list
    # This fails it the streaming is not an async generator
    response_content = b"".join([content async for content in response.streaming_content]).decode(
        "utf-8"
    )

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    assert mock_openai_stream.called

    await chat_conversation.arefresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=timezone.now(),  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Hello"],
                    "part_kind": "user-prompt",
                    "timestamp": "2025-07-25T10:36:35.297675Z",
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "Hello there", "id": None, "part_kind": "text"}],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-1234567890",
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
            "run_id": _run_id,
        },
    ]


@freeze_time("2025-07-25T10:36:35.297675Z", tick=True)
@respx.mock
@pytest.mark.asyncio
async def test_post_conversation_async_triggers_keepalive(
    api_client, mock_openai_stream_slow, monkeypatch, caplog, settings
):
    """Test posting messages to a conversation using the 'data' protocol."""
    monkeypatch.setenv("PYTHON_SERVER_MODE", "async")

    settings.KEEPALIVE_INTERVAL = 1  # s

    chat_conversation = await sync_to_async(ChatConversationFactory)(owner__language="en-us")

    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=data"
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
    await api_client.aforce_login(chat_conversation.owner)

    caplog.clear()
    caplog.set_level(level=logging.DEBUG, logger="chat.views")

    response = await sync_to_async(api_client.post)(url, data, format="json")  # client is sync

    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming

    assert "Using ASYNC streaming for chat conversation" in caplog.text

    # Wait for the streaming content to be fully received => async iterator -> list
    # This fails it the streaming is not an async generator
    response_content = b"".join([content async for content in response.streaming_content]).decode(
        "utf-8"
    )

    # Replace UUIDs with placeholders for assertion
    response_content = replace_uuids_with_placeholder(response_content)

    assert response_content == (
        '0:"Hello"\n'
        '2:[{"status": "WAITING"}]\n'
        '0:" there"\n'
        'f:{"messageId":"<mocked_uuid>"}\n'
        'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'
    )

    assert mock_openai_stream_slow.called

    await chat_conversation.arefresh_from_db()
    assert chat_conversation.ui_messages == [
        {
            "content": "Hello",
            "createdAt": "2025-07-03T15:22:17.105Z",
            "id": "yuPoOuBkKA4FnKvk",
            "parts": [{"text": "Hello", "type": "text"}],
            "role": "user",
        }
    ]

    assert len(chat_conversation.messages) == 2

    assert chat_conversation.messages[0].id == IsUUID(4)
    assert chat_conversation.messages[0] == UIMessage(
        id=chat_conversation.messages[0].id,  # don't test the message ID here
        createdAt=chat_conversation.messages[0].createdAt,  # Mocked timestamp
        content="Hello",
        reasoning=None,
        experimental_attachments=None,
        role="user",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello")],
    )

    assert chat_conversation.messages[1].id == IsUUID(4)
    assert chat_conversation.messages[1] == UIMessage(
        id=chat_conversation.messages[1].id,  # don't test the message ID here
        createdAt=chat_conversation.messages[1].createdAt,  # Mocked timestamp
        content="Hello there",
        reasoning=None,
        experimental_attachments=None,
        role="assistant",
        annotations=None,
        toolInvocations=None,
        parts=[TextUIPart(type="text", text="Hello there")],
    )

    _run_id = chat_conversation.pydantic_messages[0]["run_id"]

    # using ANY because time is not frozen in this api mock
    assert chat_conversation.pydantic_messages == [
        {
            "instructions": (
                "You are a helpful test assistant :)\n\n"
                "Today is Friday 25/07/2025.\n\nAnswer in english."
            ),
            "kind": "request",
            "parts": [
                {
                    "content": ["Hello"],
                    "part_kind": "user-prompt",
                    "timestamp": ANY,
                },
            ],
            "run_id": _run_id,
        },
        {
            "finish_reason": "stop",
            "kind": "response",
            "model_name": "test-model",
            "parts": [{"content": "Hello there", "id": None, "part_kind": "text"}],
            "provider_details": {"finish_reason": "stop"},
            "provider_name": "openai",
            "provider_response_id": "chatcmpl-1234567890",
            "timestamp": ANY,
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
            "run_id": _run_id,
        },
    ]
