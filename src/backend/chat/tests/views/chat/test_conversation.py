"""Unit tests for chat conversation actions in the chat API view."""

import json

import httpx
import pytest
import respx
from rest_framework import status

from core.factories import UserFactory

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

    return settings


@pytest.fixture(name="mock_openai_stream")
def fixture_mock_openai_stream():
    """
    Fixture to mock the OpenAI stream response.

    See https://platform.openai.com/docs/api-reference/chat-streaming/streaming
    """
    openai_stream = (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {"content": "Hello"},
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
                "choices": [
                    {
                        "delta": {"content": " there"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_stream():
        for line in openai_stream.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, stream=mock_stream())
    )

    return route


@pytest.fixture(name="mock_openai_stream_image")
def fixture_mock_openai_stream_image():
    """
    Mock a very simple OpenAI stream that *mentions* the image
    in its textual reply (the real test is that the image URL is
    forwarded in the request body to the AI service).
    """
    openai_stream = (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {"content": "I see a cat"},
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
                "choices": [
                    {
                        "delta": {"content": " in the picture."},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_stream():
        for line in openai_stream.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, stream=mock_stream())
    )
    return route


@pytest.fixture(name="mock_openai_stream_tool")
def fixture_mock_openai_stream_tool():
    """
    Mock both API calls in the tool call flow:
    1. First call returns function call
    2. Second call returns final answer after tool execution
    """

    # First response - tool call
    first_response = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-tool-call",
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                                    "type": "function",
                                    "function": {
                                        "name": "get_current_weather",
                                        "arguments": '{"location":"Paris", "unit":"celsius"}',
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-tool-call",
                "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    # Second response - final answer
    second_response = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"role": "assistant"}, "index": 0}],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "choices": [
                    {"delta": {"content": "The current weather in Paris is nice"}, "index": 0}
                ],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_first_response_stream():
        for line in first_response.splitlines(keepends=True):
            yield line.encode()

    async def mock_second_response_stream():
        for line in second_response.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        side_effect=[
            httpx.Response(200, stream=mock_first_response_stream()),
            httpx.Response(200, stream=mock_second_response_stream()),
        ]
    )

    return route


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
    assert "No messages provided" in response.data["error"]


def test_post_conversation_invalid_protocol(api_client):
    """Test posting with an invalid protocol returns a 400 error."""
    chat_conversation = ChatConversationFactory()
    url = f"/api/v1.0/chats/{chat_conversation.pk}/conversation/?protocol=invalid"
    data = {"messages": [{"role": "user", "content": "Hello there"}]}
    api_client.force_login(chat_conversation.owner)
    response = api_client.post(url, data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid protocol" in response.data["error"]


@respx.mock
def test_post_conversation_data_protocol(api_client, mock_openai_stream):
    """Test posting messages to a conversation using the 'data' protocol."""
    chat_conversation = ChatConversationFactory()

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
    assert response_content == (
        '0:"Hello"\n'
        '0:" there"\n'
        'd:{"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}}\n'
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
    assert chat_conversation.messages[0] == {
        "content": "Hello",
        "createdAt": "2025-07-03T15:22:17.105Z",
        "id": "yuPoOuBkKA4FnKvk",
        "parts": [{"text": "Hello", "type": "text"}],
        "role": "user",
    }

    assert chat_conversation.messages[1].pop("id")  # Remove ID for comparison
    assert chat_conversation.messages[1] == {
        "annotations": None,
        "content": "Hello there",
        "createdAt": None,
        "experimental_attachments": None,
        "parts": [{"text": "Hello there", "type": "text"}],
        "reasoning": None,
        "role": "assistant",
        "toolInvocations": None,
    }


@respx.mock
def test_post_conversation_text_protocol(api_client, mock_openai_stream):
    """Test posting messages to a conversation using the 'text' protocol."""
    chat_conversation = ChatConversationFactory()

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
    assert chat_conversation.messages[0] == {
        "content": "Hello",
        "createdAt": "2025-07-03T15:22:17.105Z",
        "id": "yuPoOuBkKA4FnKvk",
        "parts": [{"text": "Hello", "type": "text"}],
        "role": "user",
    }

    assert chat_conversation.messages[1].pop("id")
    assert chat_conversation.messages[1] == {
        "annotations": None,
        "content": "Hello there",
        "createdAt": None,
        "experimental_attachments": None,
        "parts": [{"text": "Hello there", "type": "text"}],
        "reasoning": None,
        "role": "assistant",
        "toolInvocations": None,
    }


@respx.mock
def test_post_conversation_with_image(api_client, mock_openai_stream_image):
    """Ensure an image URL is correctly forwarded to the AI service."""
    chat_conversation = ChatConversationFactory()
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
                        "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD",
                        "name": "FELV-cat.jpg",
                        "contentType": "image/jpeg",
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
    assert response_content == (
        '0:"I see a cat"\n'
        '0:" in the picture."\n'
        'd:{"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": '
        "0}}\n"
    )

    # --- Verify the outgoing HTTP request body contains the image ---
    request_sent = mock_openai_stream_image.calls[0].request
    body = json.loads(request_sent.content)

    # Check the exact structure expected by the AI service
    assert body["messages"] == [
        {
            "content": "You are a helpful assistant. Escape formulas or any math "
            "notation between `$$`, like `$$x^2 + y^2 = z^2$$` or `$$C_l$$`. "
            "You can use Markdown to format your answers. ",
            "role": "system",
        },
        {
            "content": [
                {"text": "Hello, what do you see on this picture?", "type": "text"},
                {
                    "image_url": {
                        "detail": "auto",
                        "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD",
                    },
                    "type": "image_url",
                },
            ],
            "role": "user",
        },
    ]
    assert body["model"] == "test-model"
    assert body["stream"] is True


@respx.mock
def test_post_conversation_tool_call(api_client, mock_openai_stream_tool, settings):
    """Ensure tool calls are correctly forwarded and streamed back."""
    settings.AI_AGENT_TOOLS = ["get_current_weather"]

    chat_conversation = ChatConversationFactory()
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
    assert response_content == (
        '9:{"toolCallId": "xLDcIljdsDrz0idal7tATWSMm2jhMj47", "toolName": '
        '"get_current_weather", "args": {"location": "Paris", "unit": "celsius"}}\n'
        'a:{"toolCallId": "xLDcIljdsDrz0idal7tATWSMm2jhMj47", "result": '
        "\"{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}\"}\n"
        '0:"The current weather in Paris is nice"\n'
        'd:{"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": '
        "0}}\n"
    )

    # --- Verify the outgoing HTTP request body ---
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    assert body["messages"] == [
        {
            "content": "You are a helpful assistant. Escape formulas or any math "
            "notation between `$$`, like `$$x^2 + y^2 = z^2$$` or `$$C_l$$`. "
            "You can use Markdown to format your answers. ",
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
    assert chat_conversation.messages[0] == {
        "content": "Weather in Paris?",
        "createdAt": "2025-07-18T12:00:00Z",
        "id": "tool-msg-1",
        "parts": [{"text": "Weather in Paris?", "type": "text"}],
        "role": "user",
    }

    assert chat_conversation.messages[1].pop("id")
    assert chat_conversation.messages[1] == {
        "annotations": None,
        "content": "The current weather in Paris is nice",
        "createdAt": None,
        "experimental_attachments": None,
        "parts": [{"text": "The current weather in Paris is nice", "type": "text"}],
        "reasoning": None,
        "role": "assistant",
        "toolInvocations": None,
    }
    # To be fixed, because in real life, the tool invocation is added to the message...
    # assert chat_conversation.messages[1] == {
    #     "annotations": None,
    #     "content": "The weather is sunny",
    #     "createdAt": None,
    #     "experimental_attachments": None,
    #     "parts": [
    #         {
    #             "type": "tool-invocation",
    #             "toolInvocation": {
    #                 "args": {"unit": "celsius", "location": "Paris"},
    #                 "step": 0,
    #                 "state": "result",
    #                 "result": "{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}",
    #                 "toolName": "get_current_weather",
    #                 "toolCallId": "FCBUEY5SpcsaB72P9taJR7Bcx0bAuqOu",
    #             },
    #         },
    #         {"text": "The weather is sunny", "type": "text"},
    #     ],
    #     "reasoning": None,
    #     "role": "assistant",
    #     "toolInvocations": [
    #         {
    #             "args": {"unit": "celsius", "location": "Paris"},
    #             "step": 0,
    #             "state": "result",
    #             "result": "{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}",
    #             "toolName": "get_current_weather",
    #             "toolCallId": "FCBUEY5SpcsaB72P9taJR7Bcx0bAuqOu",
    #         }
    #     ],
    # }


@respx.mock
def test_post_conversation_tool_call_fails(api_client, mock_openai_stream_tool, settings):
    """Ensure tool calls are correctly forwarded and streamed back when failing."""
    settings.AI_AGENT_TOOLS = []

    chat_conversation = ChatConversationFactory()
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
    assert response_content == (
        '3:"Tool get_current_weather not found in agent Conversations Assistant"\n'
        'd:{"finishReason": "error", "usage": {"promptTokens": 0, "completionTokens": '
        "0}}\n"
    )

    # --- Verify the outgoing HTTP request body ---
    request_sent = mock_openai_stream_tool.calls[0].request
    body = json.loads(request_sent.content)

    assert body["messages"] == [
        {
            "content": "You are a helpful assistant. Escape formulas or any math "
            "notation between `$$`, like `$$x^2 + y^2 = z^2$$` or `$$C_l$$`. "
            "You can use Markdown to format your answers. ",
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

    assert len(chat_conversation.messages) == 1
    assert chat_conversation.messages[0] == {
        "content": "Weather in Paris?",
        "createdAt": "2025-07-18T12:00:00Z",
        "id": "tool-msg-1",
        "parts": [{"text": "Weather in Paris?", "type": "text"}],
        "role": "user",
    }
