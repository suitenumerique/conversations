"""This module defines the data structures used in the Vercel AI SDK for chat interactions."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, field_validator, model_validator

TOOL_PART_PREFIX = "tool-"

# Stand-in for a v4 attachment stored without a content type.
DEFAULT_MEDIA_TYPE = "application/octet-stream"

# v4 tool-invocation states, mapped to their v5 equivalent.
TOOL_STATE_V4_TO_V5 = {
    "partial-call": "input-streaming",
    "call": "input-available",
    "result": "output-available",
}

# JSONValue type
JSONValue = Union[None, str, int, float, bool, Dict[str, Any], List[Any]]


# ToolCall and ToolResult
class ToolCall(BaseModel):
    """
    Represents a call to a tool with arguments.

    Attributes:
        toolCallId: A unique identifier for the tool call.
        toolName: The name of the tool being called.
        args: The arguments passed to the tool.
    """

    toolCallId: str
    toolName: str
    args: Optional[Dict[str, Any]] = None


class ToolResult(BaseModel):
    """
    Represents the result of a tool call including the original call details.

    Attributes:
        toolCallId: A unique identifier for the tool call.
        toolName: The name of the tool that was called.
        args: The arguments that were passed to the tool.
        result: The result returned by the tool.
    """

    toolCallId: str
    toolName: str
    args: Optional[Dict[str, Any]] = None
    result: Any


# ToolInvocation union
class ToolInvocationPartialCall(ToolCall):
    """
    Represents a tool call that is in progress with partial arguments.

    Attributes:
        state: The state of the tool invocation, fixed to 'partial-call'.
        step: Optional step number to track the sequence of tool invocations.
    """

    state: Literal["partial-call"]
    step: Optional[int] = None


class ToolInvocationCall(ToolCall):
    """
    Represents a complete tool call ready for execution.

    Attributes:
        state: The state of the tool invocation, fixed to 'call'.
        step: Optional step number to track the sequence of tool invocations.
    """

    state: Literal["call"]
    step: Optional[int] = None


class ToolInvocationResult(ToolResult):
    """
    Represents a completed tool call with its result.

    Attributes:
        state: The state of the tool invocation, fixed to 'result'.
        step: Optional step number to track the sequence of tool invocations.
    """

    state: Literal["result"]
    step: Optional[int] = None


ToolInvocation = Union[ToolInvocationPartialCall, ToolInvocationCall, ToolInvocationResult]


# Attachment
class Attachment(BaseModel):
    """
    Represents a file attachment that can be sent with a message.

    Attributes:
        name: Optional name of the attachment, usually the filename.
        contentType: Optional MIME type of the attachment.
        url: The URL of the attachment, can be a hosted URL or Data URL.
        skipped: Optional marker stamped by the backend when this attachment was
            kept on the persisted message but excluded from what the model saw,
            e.g. an image attached to a chat now pinned to a text-only model.
            Shape: ``{"reason": "<short_code>"}``.
    """

    name: Optional[str] = None
    contentType: Optional[str] = None
    url: str
    skipped: Optional[Dict[str, Any]] = None


# Reasoning details
class ReasoningDetailText(BaseModel):
    """
    Represents a text-based reasoning detail in a message.

    Attributes:
        type: The type of reasoning detail, fixed to 'text'.
        text: The text content of the reasoning.
        signature: Optional signature associated with the reasoning.
    """

    type: Literal["text"]
    text: str
    signature: Optional[str] = None


class ReasoningDetailRedacted(BaseModel):
    """
    Represents a redacted reasoning detail in a message.

    Attributes:
        type: The type of reasoning detail, fixed to 'redacted'.
        data: The redacted content.
    """

    type: Literal["redacted"]
    data: str


ReasoningDetail = Union[ReasoningDetailText, ReasoningDetailRedacted]


# UIParts
class TextUIPart(BaseModel):
    """
    Represents a text part of a message.

    Attributes:
        type: The type of UI part, fixed to 'text'.
        text: The text content.
    """

    type: Literal["text"]
    text: str


class ReasoningUIPart(BaseModel):
    """
    Represents a reasoning part of a message.

    Attributes:
        type: The type of UI part, fixed to 'reasoning'.
        text: The reasoning text.
    """

    type: Literal["reasoning"]
    text: str


class ToolUIPart(BaseModel):
    """
    Represents a tool invocation part of a message.

    Attributes:
        type: The type of UI part, ``tool-<toolName>``.
        toolCallId: A unique identifier for the tool call.
        state: How far the invocation got.
        input: The arguments the tool was called with.
        output: The result the tool returned, once it has one.
        errorText: The failure message, when the invocation errored.
    """

    type: str
    toolCallId: str
    state: Literal["input-streaming", "input-available", "output-available", "output-error"]
    input: Optional[Any] = None
    output: Optional[Any] = None
    errorText: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _check_tool_type(cls, value: str) -> str:
        """The part type carries the tool name, so it must be prefixed."""
        if not value.startswith(TOOL_PART_PREFIX) or value == TOOL_PART_PREFIX:
            raise ValueError(f"Tool part type must be '{TOOL_PART_PREFIX}<name>', got {value!r}")
        return value

    @property
    def tool_name(self) -> str:
        """The name of the invoked tool."""
        return self.type[len(TOOL_PART_PREFIX) :]


class LanguageModelV1Source(BaseModel):
    """
    Represents a source that has been used as input to generate the response.

    Attributes:
        sourceType: A URL source. This is return by web search RAG models.
        id: The ID of the source.
        url: The URL of the source.
        title: The title of the source.
        providerMetadata: Additional provider metadata for the source.
    """

    sourceType: Literal["url"]
    id: str
    url: str
    title: Optional[str] = None
    providerMetadata: Dict[str, Any]  # LanguageModelV1ProviderMetadata


class SourceUrlUIPart(BaseModel):
    """
    Represents a URL source part of a message.

    Attributes:
        type: The type of UI part, fixed to 'source-url'.
        sourceId: The ID of the source.
        url: The URL of the source.
        title: The title of the source.
    """

    type: Literal["source-url"]
    sourceId: str
    url: str
    title: Optional[str] = None


class FileUIPart(BaseModel):
    """
    Represents a file part of a message.

    Attributes:
        type: The type of UI part, fixed to 'file'.
        mediaType: The MIME type of the file.
        url: The file URL, either hosted or a data URL.
        filename: Optional name of the file.
        skipped: Optional marker stamped by the backend when this file was kept
            on the persisted message but excluded from what the model saw, e.g.
            an image attached to a chat now pinned to a text-only model.
            Shape: ``{"reason": "<short_code>"}``.
    """

    type: Literal["file"]
    mediaType: str
    url: str
    filename: Optional[str] = None
    skipped: Optional[Dict[str, Any]] = None


class StepStartUIPart(BaseModel):
    """
    Represents a step boundary part of a message.

    Attributes:
        type: The type of UI part, fixed to 'step-start'.
    """

    type: Literal["step-start"]


UIPart = Union[
    TextUIPart,
    ReasoningUIPart,
    ToolUIPart,
    SourceUrlUIPart,
    FileUIPart,
    StepStartUIPart,
]


def upconvert_v4_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Bring a v4-shaped message dict up to the v5 shape, in place.

    Conversations stored before the SDK v5 upgrade (and any client still posting
    v4 messages) go through this on their way in; it is idempotent, so a v5
    message passes through untouched.
    """
    parts = [_upconvert_v4_part(part) for part in message.get("parts") or []]

    # v5 carries files as parts rather than a message-level list. `contentType`
    # was optional in v4 while `mediaType` is required here, and this runs on
    # every read: without a fallback one such attachment would fail validation
    # and take down the whole conversation.
    for attachment in message.pop("experimental_attachments", None) or []:
        parts.append(
            {
                "type": "file",
                "mediaType": attachment.get("contentType") or DEFAULT_MEDIA_TYPE,
                "url": attachment.get("url"),
                "filename": attachment.get("name"),
                "skipped": attachment.get("skipped"),
            }
        )

    # The deprecated `content` was the only text of messages stored before parts
    # were populated; keep it readable by giving it a part of its own.
    content = message.get("content")
    if content and not any(_part_type(part) == "text" for part in parts):
        parts.insert(0, {"type": "text", "text": content})

    message["parts"] = parts

    # Annotations became message metadata; this is where the CO2 impact lives.
    annotations = message.pop("annotations", None)
    if annotations:
        metadata = dict(message.get("metadata") or {})
        for annotation in annotations:
            if isinstance(annotation, dict):
                metadata.update(annotation)
        message["metadata"] = metadata

    return message


def _part_type(part: Any) -> Optional[str]:
    """The ``type`` of a part, which may still be a raw dict or already a model."""
    return part.get("type") if isinstance(part, dict) else getattr(part, "type", None)


def _upconvert_v4_tool_part(part: Dict[str, Any]) -> Dict[str, Any]:
    """Bring a v4 ``tool-invocation`` part up to its v5 ``tool-<name>`` shape."""
    invocation = part.get("toolInvocation") or {}
    state = TOOL_STATE_V4_TO_V5.get(invocation.get("state"))
    if state is None:
        # An invocation stored (or posted) without a known state: only the
        # presence of a result says whether it ran to completion, and
        # `output-available` with no output would render as a tool call
        # that answered nothing.
        state = "output-available" if "result" in invocation else "input-available"

    upconverted = {
        "type": f"{TOOL_PART_PREFIX}{invocation.get('toolName')}",
        "toolCallId": invocation.get("toolCallId"),
        "state": state,
        "input": invocation.get("args"),
    }
    if "result" in invocation:
        upconverted["output"] = invocation["result"]
    return upconverted


def _upconvert_v4_part(part: Dict[str, Any]) -> Dict[str, Any]:
    """Bring a single v4 message part up to its v5 shape."""
    if not isinstance(part, dict):
        return part

    part_type = part.get("type")

    if part_type == "tool-invocation":
        return _upconvert_v4_tool_part(part)

    if part_type == "reasoning" and "text" not in part:
        return {"type": "reasoning", "text": part.get("reasoning", "")}

    if part_type == "source":
        source = part.get("source") or {}
        return {
            "type": "source-url",
            "sourceId": source.get("id"),
            "url": source.get("url"),
            "title": source.get("title"),
        }

    if part_type == "file" and "data" in part:
        return {
            "type": "file",
            "mediaType": part.get("mimeType"),
            "url": f"data:{part.get('mimeType')};base64,{part['data']}",
        }

    return part


# Message and related types
class Message(BaseModel):
    """
    Represents a message in a chat conversation.

    Attributes:
        id: A unique identifier for the message.
        createdAt: Optional timestamp when the message was created.
        role: The role of the sender (system, user, assistant, or data).
        metadata: Optional per-message metadata (token usage, CO2 impact...).
        parts: Optional list of UI parts that make up the message content.
    """

    id: str
    createdAt: Optional[datetime] = None
    content: Optional[str] = None  # deprecated, use parts instead
    role: Literal["system", "user", "assistant", "data"]
    metadata: Optional[Dict[str, Any]] = None
    parts: Optional[List[UIPart]] = None

    @model_validator(mode="before")
    @classmethod
    def _upconvert(cls, value):
        """Accept v4-shaped messages: stored history and older clients send them."""
        if isinstance(value, dict):
            return upconvert_v4_message(dict(value))
        return value


class UIMessage(Message):
    """
    Represents a message with UI parts for rendering in the user interface.

    Attributes:
        parts: List of UI parts that make up the message content.
    """

    parts: List[UIPart]


class CreateMessage(BaseModel):
    """
    Model for creating a new message.

    Attributes:
        createdAt: Optional timestamp when the message was created.
        content: The text content of the message.
        reasoning: Optional reasoning for the message.
        experimental_attachments: Optional list of attachments.
        role: The role of the sender (system, user, assistant, or data).
        data: Optional JSON value for data messages.
        annotations: Optional list of annotations.
        toolInvocations: Optional list of tool invocations.
        parts: Optional list of UI parts that make up the message content.
        id: Optional unique identifier for the message.
    """

    createdAt: Optional[datetime] = None
    content: str
    reasoning: Optional[str] = None
    experimental_attachments: Optional[List[Attachment]] = None
    role: Literal["system", "user", "assistant", "data"]
    data: Optional[JSONValue] = None
    annotations: Optional[List[JSONValue]] = None
    toolInvocations: Optional[List[ToolInvocation]] = None
    parts: Optional[List[UIPart]] = None
    id: Optional[str] = None


class ChatRequest(BaseModel):
    """
    Represents a request to the chat API.

    Attributes:
        headers: Optional request headers.
        body: Optional request body.
        messages: List of messages in the conversation.
        data: Optional additional data for the request.
    """

    headers: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None
    messages: List[Message]
    data: Optional[JSONValue] = None


class ChatRequestOptions(BaseModel):
    """
    Options for a chat request.

    Attributes:
        headers: Optional request headers.
        body: Optional request body.
        data: Optional additional data for the request.
        experimental_attachments: Optional list of attachments.
        allowEmptySubmit: Optional flag to allow empty message submission.
    """

    headers: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None
    data: Optional[JSONValue] = None
    experimental_attachments: Optional[List[Attachment]] = None
    allowEmptySubmit: Optional[bool] = None


class UseChatOptions(BaseModel):
    """
    Options for the useChat hook.

    Attributes:
        keepLastMessageOnError: Optional flag to keep the last message on error.
        api: Optional API endpoint.
        id: Optional unique identifier for the chat.
        initialMessages: Optional initial messages for the chat.
        initialInput: Optional initial input for the chat.
        credentials: Optional credentials for the request.
        headers: Optional request headers.
        body: Optional request body.
        sendExtraMessageFields: Optional flag to send extra message fields.
        streamProtocol: Optional stream protocol to use.
    """

    keepLastMessageOnError: Optional[bool] = None
    api: Optional[str] = None
    id: Optional[str] = None
    initialMessages: Optional[List[Message]] = None
    initialInput: Optional[str] = None
    credentials: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None
    sendExtraMessageFields: Optional[bool] = None
    streamProtocol: Optional[Literal["data", "text"]] = None


class UseCompletionOptions(BaseModel):
    """
    Options for the useCompletion hook.

    Attributes:
        api: Optional API endpoint.
        id: Optional unique identifier for the completion.
        initialInput: Optional initial input for the completion.
        initialCompletion: Optional initial completion result.
        credentials: Optional credentials for the request.
        headers: Optional request headers.
        body: Optional request body.
        streamProtocol: Optional stream protocol to use.
    """

    api: Optional[str] = None
    id: Optional[str] = None
    initialInput: Optional[str] = None
    initialCompletion: Optional[str] = None
    credentials: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None
    streamProtocol: Optional[Literal["data", "text"]] = None


class LanguageModelUsage(BaseModel):
    """
    Represents the token usage in a language model interaction.

    Attributes:
        promptTokens: Number of tokens used in the prompt.
        completionTokens: Number of tokens used in the completion.
        totalTokens: Total number of tokens used.
    """

    promptTokens: int
    completionTokens: int
    totalTokens: int


class AssistantMessageContentText(BaseModel):
    """
    Represents text content in an assistant message.

    Attributes:
        type: The type of content, fixed to 'text'.
        text: Dictionary containing the text value.
    """

    type: Literal["text"]
    text: Dict[str, str]  # {'value': str}


class AssistantMessage(BaseModel):
    """
    Represents a message from the assistant.

    Attributes:
        id: A unique identifier for the message.
        role: The role of the sender, fixed to 'assistant'.
        content: List of content blocks in the message.
    """

    id: str
    role: Literal["assistant"]
    content: List[AssistantMessageContentText]


class DataMessage(BaseModel):
    """
    Represents a data message.

    Attributes:
        id: Optional unique identifier for the message.
        role: The role of the sender, fixed to 'data'.
        data: The JSON data contained in the message.
    """

    id: Optional[str] = None
    role: Literal["data"]
    data: JSONValue
