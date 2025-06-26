"""Tests for OpenAI client message conversion."""

# pylint: disable=protected-access

import pytest

from chat.ai_sdk_types import (
    Attachment,
    TextUIPart,
    ToolInvocationResult,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.clients.openai import AIAgentService


@pytest.fixture(autouse=True)
def openai_settings(settings):
    """Create a mock AIAgentService for testing."""
    settings.AI_BASE_URL = "http://test.url"
    settings.AI_API_KEY = "test_key"
    settings.AI_MODEL = "test_model"


def test_convert_simple_text_messages():
    """Test conversion of simple text messages"""
    messages = [
        UIMessage(
            id="user1",
            content="Hello, how are you?",
            role="user",
            parts=[TextUIPart(type="text", text="Hello, how are you?")],
        ),
        UIMessage(
            id="assistant1",
            content="I'm doing well, thank you!",
            role="assistant",
            parts=[TextUIPart(type="text", text="I'm doing well, thank you!")],
        ),
    ]

    result = AIAgentService._convert_to_openai_messages(messages)

    assert result == [
        {
            "role": "user",
            "type": "message",
            "content": [{"type": "input_text", "text": "Hello, how are you?"}],
        },
        {
            "role": "assistant",
            "type": "message",
            "content": [{"type": "output_text", "text": "I'm doing well, thank you!"}],
        },
    ]


def test_convert_messages_with_tool_invocations():
    """Test conversion of messages with tool invocations"""
    messages = [
        UIMessage(
            id="user1",
            content="What's the weather in Paris?",
            role="user",
            parts=[TextUIPart(type="text", text="What's the weather in Paris?")],
        ),
        UIMessage(
            id="assistant1",
            content="The current weather in Paris is 22°C.",
            role="assistant",
            toolInvocations=[
                ToolInvocationResult(
                    toolCallId="tool1",
                    toolName="get_current_weather",
                    args={"location": "Paris", "unit": "celsius"},
                    result="{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}",
                    state="result",
                    step=0,
                )
            ],
            parts=[
                ToolInvocationUIPart(
                    type="tool-invocation",
                    toolInvocation=ToolInvocationResult(
                        toolCallId="tool1",
                        toolName="get_current_weather",
                        args={"location": "Paris", "unit": "celsius"},
                        result="{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}",
                        state="result",
                        step=0,
                    ),
                ),
                TextUIPart(type="text", text="The current weather in Paris is 22°C."),
            ],
        ),
    ]

    result = AIAgentService._convert_to_openai_messages(messages)

    assert result == [
        {
            "role": "user",
            "type": "message",
            "content": [{"type": "input_text", "text": "What's the weather in Paris?"}],
        },
        {
            "role": "assistant",
            "type": "message",
            "content": [{"type": "output_text", "text": "The current weather in Paris is 22°C."}],
        },
        {
            "type": "function_call",
            "call_id": "tool1",
            "name": "get_current_weather",
            "arguments": '{"location": "Paris", "unit": "celsius"}',
            "status": "result",
        },
    ]


def test_convert_messages_with_images():
    """Test conversion of messages with images"""
    messages = [
        UIMessage(
            id="user1",
            content="What is in this image?",
            role="user",
            parts=[
                TextUIPart(type="text", text="What is in this image?"),
            ],
            experimental_attachments=[
                Attachment(
                    contentType="image/jpeg",
                    url="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                    name="image.jpg",
                )
            ],
        )
    ]

    result = AIAgentService._convert_to_openai_messages(messages)

    assert result == [
        {
            "role": "user",
            "type": "message",
            "content": [
                {"type": "input_text", "text": "What is in this image?"},
                {"type": "input_image", "image_url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="},
            ],
        }
    ]


def test_convert_messages_with_files():
    """Test conversion of messages with files"""
    messages = [
        UIMessage(
            id="user1",
            content="Here is the file",
            role="user",
            parts=[
                TextUIPart(type="text", text="Here is the file"),
            ],
            experimental_attachments=[
                Attachment(
                    contentType="text/plain",
                    url="data:text/plain;base64,SGVsbG8gV29ybGQ=",
                    name="example.txt",
                )
            ],
        )
    ]

    result = AIAgentService._convert_to_openai_messages(messages)

    assert result == [
        {
            "role": "user",
            "type": "message",
            "content": [
                {"type": "input_text", "text": "Here is the file"},
                {
                    "type": "input_file",
                    "file_data": "data:text/plain;base64,SGVsbG8gV29ybGQ=",
                    "filename": "example.txt",
                },
            ],
        }
    ]


def test_convert_messages_with_experimental_attachments():
    """Test conversion of messages with experimental attachments"""
    messages = [
        UIMessage(
            id="user1",
            content="Check these attachments",
            role="user",
            parts=[TextUIPart(type="text", text="Check these attachments")],
            experimental_attachments=[
                Attachment(
                    contentType="image/jpeg",
                    url="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                    name="image.jpg",
                ),
                Attachment(
                    contentType="text/plain",
                    url="data:text/plain;base64,SGVsbG8gV29ybGQ=",
                    name="example.txt",
                ),
            ],
        )
    ]

    result = AIAgentService._convert_to_openai_messages(messages)

    assert result == [
        {
            "role": "user",
            "type": "message",
            "content": [
                {"type": "input_text", "text": "Check these attachments"},
                {"type": "input_image", "image_url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="},
                {
                    "type": "input_file",
                    "file_data": "data:text/plain;base64,SGVsbG8gV29ybGQ=",
                    "filename": "example.txt",
                },
            ],
        }
    ]


def test_convert_complex_message_combination():
    """Test conversion of complex combination of message types"""
    messages = [
        UIMessage(
            id="user1",
            content="What is this image and what's the weather in Paris?",
            role="user",
            parts=[
                TextUIPart(type="text", text="What is this image and what's the weather in Paris?"),
            ],
            experimental_attachments=[
                Attachment(
                    contentType="image/jpeg",
                    url="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                    name="eiffel_tower.jpg",
                )
            ],
        ),
        UIMessage(
            id="assistant1",
            content="This is the Eiffel Tower. The current weather in Paris is 22°C.",
            role="assistant",
            toolInvocations=[
                ToolInvocationResult(
                    toolCallId="tool1",
                    toolName="get_current_weather",
                    args={"location": "Paris", "unit": "celsius"},
                    result="{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}",
                    state="result",
                    step=0,
                )
            ],
            parts=[
                ToolInvocationUIPart(
                    type="tool-invocation",
                    toolInvocation=ToolInvocationResult(
                        toolCallId="tool1",
                        toolName="get_current_weather",
                        args={"location": "Paris", "unit": "celsius"},
                        result="{'location': 'Paris', 'temperature': 22, 'unit': 'celsius'}",
                        state="result",
                        step=0,
                    ),
                ),
                TextUIPart(
                    type="text",
                    text="This is the Eiffel Tower. The current weather in Paris is 22°C.",
                ),
            ],
        ),
    ]

    result = AIAgentService._convert_to_openai_messages(messages)

    assert result == [
        {
            "role": "user",
            "type": "message",
            "content": [
                {
                    "type": "input_text",
                    "text": "What is this image and what's the weather in Paris?",
                },
                {"type": "input_image", "image_url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="},
            ],
        },
        {
            "role": "assistant",
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "This is the Eiffel Tower. The current weather in Paris is 22°C.",
                }
            ],
        },
        {
            "type": "function_call",
            "call_id": "tool1",
            "name": "get_current_weather",
            "arguments": '{"location": "Paris", "unit": "celsius"}',
            "status": "result",
        },
    ]
