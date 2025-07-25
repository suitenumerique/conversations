"""Tests for the conversion between UI messages and Pydantic AI messages."""

import base64
import datetime

import pytest
from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.usage import Usage

from chat.ai_sdk_types import (
    Attachment,
    FileUIPart,
    LanguageModelV1Source,
    ReasoningUIPart,
    SourceUIPart,
    StepStartUIPart,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.clients.pydantic_ui_message_converter import ui_message_to_model_message


def test_user_message_with_text():
    """Test conversion of a user message with text only."""
    timestamp = datetime.datetime.now()
    ui_message = UIMessage(
        id="msg1",
        role="user",
        content="Hello, how are you?",
        parts=[TextUIPart(type="text", text="Hello, how are you?")],
        createdAt=timestamp,
    )

    result = ui_message_to_model_message(ui_message)
    assert isinstance(result, ModelRequest)
    assert result.parts == [
        UserPromptPart(content="Hello, how are you?", timestamp=timestamp),
    ]
    assert result.instructions is None


def test_assistant_message_with_text():
    """Test conversion of an assistant message with text only."""
    ui_message = UIMessage(
        id="msg2",
        role="assistant",
        content="I'm doing well, thank you!",
        parts=[TextUIPart(type="text", text="I'm doing well, thank you!")],
    )

    result = ui_message_to_model_message(ui_message)

    assert isinstance(result, ModelResponse)
    assert result.parts == [TextPart(content="I'm doing well, thank you!")]
    assert result.usage == Usage()
    assert result.timestamp is not None


def test_assistant_message_with_tool_call():
    """Test conversion of an assistant message with a tool call."""
    tool_args = {"location": "Paris", "unit": "celsius"}
    ui_message = UIMessage(
        id="msg8",
        role="assistant",
        content="Let me check the weather for you.",
        parts=[
            TextUIPart(type="text", text="Let me check the weather for you."),
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    state="call",
                    toolCallId="call123",
                    toolName="get_weather",
                    args=tool_args,
                ),
            ),
        ],
    )

    result = ui_message_to_model_message(ui_message)

    assert isinstance(result, ModelResponse)
    assert len(result.parts) == 2
    assert isinstance(result.parts[0], TextPart)
    assert result.parts[0].content == "Let me check the weather for you."
    assert isinstance(result.parts[1], ToolCallPart)
    assert result.parts[1].tool_call_id == "call123"
    assert result.parts[1].tool_name == "get_weather"
    assert result.parts[1].args == tool_args


def test_assistant_message_with_reasoning():
    """Test conversion of an assistant message with reasoning."""
    # Arrange
    reasoning_text = "I need to think about this problem step by step..."
    ui_message = UIMessage(
        id="msg9",
        role="assistant",
        content="The answer is 42.",
        parts=[
            ReasoningUIPart(
                type="reasoning",
                reasoning=reasoning_text,
                details=[],
            ),
            TextUIPart(type="text", text="The answer is 42."),
        ],
    )

    # Act
    result = ui_message_to_model_message(ui_message)

    # Assert
    assert isinstance(result, ModelResponse)
    assert len(result.parts) == 2
    assert isinstance(result.parts[0], ThinkingPart)
    assert result.parts[0].content == reasoning_text
    assert isinstance(result.parts[1], TextPart)
    assert result.parts[1].content == "The answer is 42."


def test_multiple_text_parts():
    """Test conversion of a message with multiple text parts."""
    # Arrange
    ui_message = UIMessage(
        id="msg10",
        role="user",
        content="Hello world! How are you today?",
        parts=[
            TextUIPart(type="text", text="Hello world!"),
            TextUIPart(type="text", text=" How are you today?"),
        ],
    )

    # Act
    result = ui_message_to_model_message(ui_message)

    # Assert
    assert isinstance(result, ModelRequest)
    assert len(result.parts) == 2
    assert isinstance(result.parts[0], UserPromptPart)
    assert result.parts[0].content == "Hello world!"
    assert isinstance(result.parts[1], UserPromptPart)
    assert result.parts[1].content == " How are you today?"


def test_complex_message():
    """
    Test conversion of a conversation with user and assistant messages,
    including tool call and thinking.
    """
    user_message = UIMessage(
        id="msg_user",
        role="user",
        content="What's the weather in Paris?",
        parts=[TextUIPart(type="text", text="What's the weather in Paris?")],
        createdAt=datetime.datetime.now(),
    )
    user_result = ui_message_to_model_message(user_message)
    assert isinstance(user_result, ModelRequest)
    assert len(user_result.parts) == 1
    assert isinstance(user_result.parts[0], UserPromptPart)
    assert user_result.parts[0].content == "What's the weather in Paris?"

    # Assistant message with text, tool call, and thinking
    tool_args = {"location": "Paris", "unit": "celsius"}
    reasoning_text = "Looking up the weather for Paris."
    assistant_message = UIMessage(
        id="msg_assistant",
        role="assistant",
        content="Let me check the weather for you.",
        parts=[
            TextUIPart(type="text", text="Let me check the weather for you."),
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    state="call",
                    toolCallId="call123",
                    toolName="get_weather",
                    args=tool_args,
                ),
            ),
            ReasoningUIPart(
                type="reasoning",
                reasoning=reasoning_text,
                details=[],
            ),
        ],
    )
    assistant_result = ui_message_to_model_message(assistant_message)
    assert isinstance(assistant_result, ModelResponse)
    assert len(assistant_result.parts) == 3
    assert isinstance(assistant_result.parts[0], TextPart)
    assert assistant_result.parts[0].content == "Let me check the weather for you."
    assert isinstance(assistant_result.parts[1], ToolCallPart)
    assert assistant_result.parts[1].tool_call_id == "call123"
    assert assistant_result.parts[1].tool_name == "get_weather"
    assert assistant_result.parts[1].args == tool_args
    assert isinstance(assistant_result.parts[2], ThinkingPart)
    assert assistant_result.parts[2].content == reasoning_text


def test_assistant_message_with_string_tool_args():
    """Test conversion of an assistant message with string tool arguments."""

    ui_message = UIMessage(
        id="msg14",
        role="assistant",
        content="Let me check the weather for you.",
        parts=[
            TextUIPart(type="text", text="Let me check the weather for you."),
            ToolInvocationUIPart(
                type="tool-invocation",
                toolInvocation=ToolInvocationCall(
                    state="call",
                    toolCallId="call123",
                    toolName="get_weather",
                    args={"location": "Paris", "unit": "celsius"},
                ),
            ),
        ],
    )

    result = ui_message_to_model_message(ui_message)

    assert isinstance(result, ModelResponse)
    assert len(result.parts) == 2
    assert isinstance(result.parts[1], ToolCallPart)
    assert result.parts[1].args == {"location": "Paris", "unit": "celsius"}


def test_user_message_with_attachment():
    """Test conversion of a user message with text only."""
    timestamp = datetime.datetime.now()
    ui_message = UIMessage(
        id="msg1",
        role="user",
        content="Hello, how are you?",
        parts=[TextUIPart(type="text", text="What do you see?")],
        experimental_attachments=[
            Attachment(
                name="image.png",
                contentType="image/png",
                url=(
                    "data:image/png;base64,"
                    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ"
                    "3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII="
                ),
            )
        ],
        createdAt=timestamp,
    )

    result = ui_message_to_model_message(ui_message)
    assert isinstance(result, ModelRequest)
    assert len(result.parts) == 2
    assert result.parts[0] == UserPromptPart(content="What do you see?", timestamp=timestamp)
    assert isinstance(result.parts[1], UserPromptPart)
    assert len(result.parts[1].content) == 1
    assert isinstance(result.parts[1].content[0], BinaryContent)
    assert result.parts[1].content[0].media_type == "image/png"
    assert base64.b64encode(result.parts[1].content[0].data) == (
        b"iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ"
        b"3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII="
    )
    assert result.instructions is None


def test_assistant_message_with_attachment():
    """Test conversion of a user message with text only."""
    timestamp = datetime.datetime.now()
    ui_message = UIMessage(
        id="msg1",
        role="assistant",
        content="Hello, how are you?",
        parts=[TextUIPart(type="text", text="What do you see?")],
        experimental_attachments=[
            Attachment(
                name="image.png",
                contentType="image/png",
                url=(
                    "data:image/png;base64,"
                    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ"
                    "3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII="
                ),
            )
        ],
        createdAt=timestamp,
    )
    with pytest.raises(ValueError, match="Experimental attachments are not supported"):
        ui_message_to_model_message(ui_message)


@pytest.mark.parametrize("role", ("system", "data"))
def test_unsupported_role(role):
    """Test conversion with an unsupported role."""
    # Arrange
    ui_message = UIMessage(
        id="msg12",
        role=role,  # Unsupported role
        content="You are a helpful assistant",
        parts=[TextUIPart(type="text", text="You are a helpful assistant")],
    )

    with pytest.raises(ValueError, match=f"Unsupported message role: {role}"):
        ui_message_to_model_message(ui_message)


@pytest.mark.parametrize("role", ("user", "assistant"))
def test_message_with_source_part(role):
    """Test conversion of a user/assistant message with SourceUIPart (should raise)."""
    ui_message = UIMessage(
        id="msg_source_user",
        role=role,
        content="source info",
        parts=[
            SourceUIPart(
                type="source", source=LanguageModelV1Source(source_type="test", details={})
            )
        ],
    )
    with pytest.raises(
        ValueError, match="Unsupported UIPart type: <class 'chat.ai_sdk_types.SourceUIPart'>"
    ):
        ui_message_to_model_message(ui_message)


@pytest.mark.parametrize("role", ("user", "assistant"))
def test_message_with_step_start_part(role):
    """Test conversion of a user/assistant message with StepStartUIPart (should raise)."""
    ui_message = UIMessage(
        id="msg_step_user",
        role=role,
        content="step start",
        parts=[StepStartUIPart(type="step-start")],
    )
    with pytest.raises(
        ValueError, match="Unsupported UIPart type: <class 'chat.ai_sdk_types.StepStartUIPart'>"
    ):
        ui_message_to_model_message(ui_message)


@pytest.mark.parametrize("role", ("user", "assistant"))
def test_assistant_message_with_file_part(role):
    """Test conversion of a user/assistant message with FileUIPart (should raise)."""
    ui_message = UIMessage(
        id="msg_file_assistant",
        role=role,
        content="file part",
        parts=[FileUIPart(type="file", mimeType="image/png", data="http://example.com/image.png")],
    )
    with pytest.raises(
        ValueError, match="Unsupported UIPart type: <class 'chat.ai_sdk_types.FileUIPart'>"
    ):
        ui_message_to_model_message(ui_message)
