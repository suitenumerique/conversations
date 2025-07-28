"""Tests for converting ModelMessage to UIMessage using Pydantic AI types."""

import datetime
import json
import uuid
from unittest.mock import patch

from django.utils import timezone

import pytest
from freezegun import freeze_time
from pydantic_ai.messages import (
    AudioUrl,
    BinaryContent,
    DocumentUrl,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    UserPromptPart,
    VideoUrl,
)

from chat.ai_sdk_types import (
    Attachment,
    ReasoningDetailText,
    ReasoningUIPart,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.clients.pydantic_ui_message_converter import model_message_to_ui_message


@pytest.fixture(autouse=True)
def mock_uuid4_fixture():
    """Fixture to mock UUID generation for testing."""
    with patch("uuid.uuid4", return_value=uuid.UUID("f0cc3bb5-f207-401b-8281-4cba6202991d")):
        yield


def test_model_message_to_ui_message_text_user_full():
    """Test converting a ModelRequest with UserPromptPart containing text to UIMessage."""
    timestamp = datetime.datetime.now()
    model_message = ModelRequest(
        parts=[UserPromptPart(content="Hello!", timestamp=timestamp)], kind="request"
    )
    expected = UIMessage(
        id="f0cc3bb5-f207-401b-8281-4cba6202991d",  # Mocked UUID
        role="user",
        content="Hello!",
        parts=[TextUIPart(type="text", text="Hello!")],
        createdAt=timestamp,
    )
    result = model_message_to_ui_message(model_message)
    assert result == expected


@freeze_time()
def test_model_message_to_ui_message_text_assistant_full():
    """Test converting a ModelResponse with TextPart to UIMessage."""
    model_message = ModelResponse(parts=[TextPart(content="Hi there!")])
    expected = UIMessage(
        id="f0cc3bb5-f207-401b-8281-4cba6202991d",  # Mocked UUID
        role="assistant",
        content="Hi there!",
        parts=[TextUIPart(type="text", text="Hi there!")],
        createdAt=timezone.now(),
    )
    result = model_message_to_ui_message(model_message)
    assert result == expected


@freeze_time()
def test_model_message_to_ui_message_tool_call_full():
    """Test converting a ModelResponse with ToolCallPart to UIMessage."""
    args = {"foo": "bar"}
    model_message = ModelResponse(
        parts=[ToolCallPart(tool_call_id="id1", tool_name="tool", args=args)]
    )
    expected = UIMessage(
        id="f0cc3bb5-f207-401b-8281-4cba6202991d",  # Mocked UUID
        role="assistant",
        content="",
        parts=[
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    state="call",
                    toolCallId="id1",
                    toolName="tool",
                    args=args,
                ),
            )
        ],
        createdAt=timezone.now(),
    )
    result = model_message_to_ui_message(model_message)
    assert result == expected


@freeze_time()
def test_model_message_to_ui_message_reasoning_full():
    """Test converting a ModelResponse with ThinkingPart to UIMessage."""
    model_message = ModelResponse(parts=[ThinkingPart(content="reason", signature="sig")])
    expected = UIMessage(
        id="f0cc3bb5-f207-401b-8281-4cba6202991d",  # Mocked UUID
        role="assistant",
        content="",
        parts=[
            ReasoningUIPart(
                type="reasoning",
                reasoning="reason",
                details=[ReasoningDetailText(type="text", text="reason", signature="sig")],
            )
        ],
        createdAt=timezone.now(),
    )
    result = model_message_to_ui_message(model_message)
    assert result.id == expected.id
    assert result.role == expected.role
    assert result.content == expected.content
    assert result.createdAt == expected.createdAt
    assert len(result.parts) == 1
    parts_list = list(result.parts)
    part = parts_list[0]
    assert isinstance(part, ReasoningUIPart)
    assert part.reasoning == "reason"
    assert part.details[0].type == "text"
    assert part.details[0].text == "reason"
    assert part.details[0].signature == "sig"


def test_model_message_to_ui_message_binary_content():
    """Test converting a ModelRequest with BinaryContent to UIMessage."""
    bin_data = b"bin"
    model_message = ModelRequest(
        parts=[
            UserPromptPart(
                content=[
                    "What do you see?",
                    BinaryContent(media_type="application/octet-stream", data=bin_data),
                ]
            ),
        ],
        kind="request",
    )

    result = model_message_to_ui_message(model_message)
    assert result.role == "user"
    assert result.parts == [TextUIPart(type="text", text="What do you see?")]
    assert result.experimental_attachments == [
        Attachment(
            name=None,
            contentType="application/octet-stream",
            url="data:application/octet-stream;base64,Ymlu",
        ),
    ]


def test_model_message_to_ui_message_file_parts_full():
    """Test handling unsupported file parts in UserPromptPart content."""
    for part_type in [AudioUrl, VideoUrl, DocumentUrl]:
        model_message = ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        "Check this file",
                        part_type(url="http://example.com/file"),
                    ],
                    timestamp=None,
                ),
            ],
            kind="request",
        )

        with pytest.raises(ValueError, match="Unsupported UserContent in UserPromptPart"):
            model_message_to_ui_message(model_message)


def test_model_message_to_ui_message_empty_parts():
    """Test converting a ModelRequest with no valid parts returns None."""
    model_message = ModelRequest(parts=[], kind="request")
    assert model_message_to_ui_message(model_message) is None


def test_model_message_to_ui_message_unsupported_part():
    """Test handling unsupported part types in ModelRequest."""
    model_message = ModelRequest(parts=[SystemPromptPart(content="sys")], kind="request")
    assert model_message_to_ui_message(model_message) is None
    model_message = ModelRequest(parts=[RetryPromptPart(content="retry")], kind="request")
    assert model_message_to_ui_message(model_message) is None


def test_model_message_to_ui_message_invalid_content_type():
    """Test handling invalid content type in UserPromptPart."""

    class DummyContent:
        """Dummy class for testing invalid content types."""

    model_message = ModelRequest(
        parts=[UserPromptPart(content=[DummyContent()], timestamp=None)], kind="request"
    )
    with pytest.raises(ValueError, match="Unsupported UserContent in UserPromptPart"):
        model_message_to_ui_message(model_message)


def test_model_message_to_ui_message_invalid_response_part():
    """Test handling invalid part type in ModelResponse."""

    class DummyPart:
        """Dummy class for testing invalid part types."""

    model_message = ModelResponse(parts=[DummyPart()])
    with pytest.raises(ValueError, match="Unsupported ModelMessage part type"):
        model_message_to_ui_message(model_message)


def test_model_message_to_ui_message_multiple_text_parts():
    """Test converting a ModelResponse with multiple TextParts to UIMessage."""
    model_message = ModelResponse(parts=[TextPart(content="A"), TextPart(content="B")])
    result = model_message_to_ui_message(model_message)
    assert result.role == "assistant"
    parts_list = list(result.parts)
    assert [p.text for p in parts_list if isinstance(p, TextUIPart)] == ["A", "B"]
    assert result.content == "AB"


def test_model_message_to_ui_message_userpromptpart_list_of_str():
    """Test converting a ModelRequest with UserPromptPart containing list of strings."""
    model_message = ModelRequest(
        parts=[UserPromptPart(content=["A", "B"], timestamp=None)], kind="request"
    )
    result = model_message_to_ui_message(model_message)
    assert result.role == "user"
    parts_list = list(result.parts)
    assert [p.text for p in parts_list if isinstance(p, TextUIPart)] == ["A", "B"]
    assert result.content == "AB"


def test_model_message_to_ui_message_tool_call_args_str():
    """Test converting a ModelResponse with ToolCallPart containing JSON string args."""
    args = {"foo": "bar"}
    model_message = ModelResponse(
        parts=[ToolCallPart(tool_call_id="id1", tool_name="tool", args=json.dumps(args))]
    )
    result = model_message_to_ui_message(model_message)
    parts_list = list(result.parts)
    part = parts_list[0]
    assert isinstance(part, ToolInvocationUIPart)
    assert part.toolInvocation.args == args


def test_model_message_to_ui_message_with_reasoning_signature_none():
    """Test converting a ModelResponse with ThinkingPart having signature=None."""
    model_message = ModelResponse(parts=[ThinkingPart(content="reason", signature=None)])
    result = model_message_to_ui_message(model_message)
    parts_list = list(result.parts)
    part = parts_list[0]
    assert isinstance(part, ReasoningUIPart)
    assert part.details[0].signature is None


def test_model_message_to_ui_message_created_at_response():
    """Test converting a ModelResponse with a specific timestamp."""
    model_message = ModelResponse(
        parts=[TextPart(content="Hi!")], timestamp=datetime.datetime(2024, 1, 1, 12, 0, 0)
    )
    result = model_message_to_ui_message(model_message)
    assert result.createdAt == datetime.datetime(2024, 1, 1, 12, 0, 0)
