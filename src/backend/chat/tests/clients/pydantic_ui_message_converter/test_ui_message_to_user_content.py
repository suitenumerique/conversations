"""Tests for the conversion from UIMessage to UserContent list."""

import base64
import datetime

from pydantic_ai.messages import BinaryContent, DocumentUrl

from chat.ai_sdk_types import (
    FileUIPart,
    ReasoningUIPart,
    TextUIPart,
    ToolUIPart,
    UIMessage,
)
from chat.clients.pydantic_ui_message_converter import ui_message_to_user_content


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

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], str)
    assert result[0] == "Hello, how are you?"


def test_user_message_with_multiple_text_parts():
    """Test conversion of a user message with multiple text parts."""
    ui_message = UIMessage(
        id="msg2",
        role="user",
        content="Hello world! How are you today?",
        parts=[
            TextUIPart(type="text", text="Hello world!"),
            TextUIPart(type="text", text=" How are you today?"),
        ],
    )

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == "Hello world!"
    assert result[1] == " How are you today?"


def test_user_message_with_file():
    """Test conversion of a user message with a file part."""
    file_content = b"This is a text file content"
    mime_type = "text/plain"
    data_url = f"data:{mime_type};base64,{base64.b64encode(file_content).decode()}"

    ui_message = UIMessage(
        id="msg3",
        role="user",
        content="Check this file",
        parts=[
            TextUIPart(type="text", text="Check this file"),
            FileUIPart(type="file", url=data_url, mediaType=mime_type, filename="example.txt"),
        ],
    )

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == "Check this file"
    assert isinstance(result[1], BinaryContent)
    assert result[1].data == file_content
    assert result[1].media_type == mime_type


def test_user_message_with_v4_experimental_attachment():
    """A message stored before the v5 upgrade still converts: the shim moves its
    ``experimental_attachments`` onto file parts."""
    content_type = "image/png"
    sample_data = b"sample image data"
    base64_data = base64.b64encode(sample_data).decode("utf-8")
    data_url = f"data:{content_type};base64,{base64_data}"

    ui_message = UIMessage.model_validate(
        {
            "id": "msg4",
            "role": "user",
            "content": "Check this image",
            "parts": [{"type": "text", "text": "Check this image"}],
            "experimental_attachments": [{"contentType": content_type, "url": data_url}],
        }
    )

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == "Check this image"
    assert isinstance(result[1], BinaryContent)
    assert result[1].data == sample_data
    assert result[1].media_type == content_type


def test_user_message_with_multiple_attachments():
    """Test conversion of a user message with multiple attachments of different types."""
    # First attachment - text file
    file_content = "This is a text file content"
    file_mime_type = "text/plain"

    # Second attachment - image
    image_content_type = "image/png"
    image_data = b"sample image data"
    base64_image = base64.b64encode(image_data).decode("utf-8")
    image_data_url = f"data:{image_content_type};base64,{base64_image}"

    file_data_url = (
        f"data:{file_mime_type};base64,{base64.b64encode(file_content.encode()).decode()}"
    )
    ui_message = UIMessage(
        id="msg5",
        role="user",
        content="Check these files",
        parts=[
            TextUIPart(type="text", text="Check these files"),
            FileUIPart(
                type="file",
                url=file_data_url,
                mediaType=file_mime_type,
                filename="example.txt",
            ),
            FileUIPart(type="file", url=image_data_url, mediaType=image_content_type),
        ],
    )

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0] == "Check these files"

    assert isinstance(result[1], BinaryContent)
    assert result[1].data == file_content.encode("utf-8")
    assert result[1].media_type == file_mime_type

    assert isinstance(result[2], BinaryContent)
    assert result[2].data == image_data
    assert result[2].media_type == image_content_type


def test_user_message_with_tool_invocation():
    """Test conversion of a user message with a tool invocation part."""
    tool_args = {"query": "weather in Paris", "unit": "celsius"}
    ui_message = UIMessage(
        id="msg6",
        role="user",
        content="Check the weather",
        parts=[
            TextUIPart(type="text", text="Check the weather"),
            ToolUIPart(
                type="tool-get_weather",
                toolCallId="call123",
                state="input-available",
                input=tool_args,
            ),
        ],
    )

    result = ui_message_to_user_content(ui_message)

    # Tool invocation parts are skipped in the conversion
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == "Check the weather"


def test_user_message_with_reasoning():
    """Test conversion of a user message with a reasoning part."""
    reasoning_text = "I need to think about this..."
    ui_message = UIMessage(
        id="msg7",
        role="user",
        content="Let me think",
        parts=[
            TextUIPart(type="text", text="Let me think"),
            ReasoningUIPart(type="reasoning", text=reasoning_text),
        ],
    )

    result = ui_message_to_user_content(ui_message)

    # Reasoning parts are skipped in the conversion
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == "Let me think"


def test_hosted_file_url():
    """Test conversion of a user message with a hosted (non data URL) file part."""
    ui_message = UIMessage(
        id="msg8",
        role="user",
        content="Check this file",
        parts=[
            TextUIPart(type="text", text="Check this file"),
            FileUIPart(
                type="file",
                url="https://example.com/file.txt",  # Not a data URL
                mediaType="text/plain",
            ),
        ],
    )

    result = ui_message_to_user_content(ui_message)
    assert result == [
        "Check this file",
        DocumentUrl(url="https://example.com/file.txt", _media_type="text/plain"),
    ]


def test_empty_message():
    """Test conversion of a user message with no parts."""
    ui_message = UIMessage(
        id="msg10",
        role="user",
        content="",
        parts=[],
    )

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 0


def test_assistant_message():
    """Test conversion of an assistant message."""
    ui_message = UIMessage(
        id="msg11",
        role="assistant",
        content="I'm an assistant",
        parts=[TextUIPart(type="text", text="I'm an assistant")],
    )

    result = ui_message_to_user_content(ui_message)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == "I'm an assistant"
