"""This module defines the data structures used in the Vercel AI SDK for chat interactions."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel

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
    args: Dict[str, Any]


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
    args: Dict[str, Any]
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
    """

    name: Optional[str] = None
    contentType: Optional[str] = None
    url: str


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
        reasoning: The reasoning text.
        details: List of reasoning details.
    """

    type: Literal["reasoning"]
    reasoning: str
    details: List[ReasoningDetail]


class ToolInvocationUIPart(BaseModel):
    """
    Represents a tool invocation part of a message.

    Attributes:
        type: The type of UI part, fixed to 'tool-invocation'.
        toolInvocation: The tool invocation details.
    """

    type: Literal["tool-invocation"]
    toolInvocation: ToolInvocation


class LanguageModelV1Source(BaseModel):
    """
    Represents source information from a language model.

    Attributes:
        source_type: The type of source.
        details: Additional details about the source.
    """

    source_type: str
    details: Dict[str, Any]


class SourceUIPart(BaseModel):
    """
    Represents a source part of a message.

    Attributes:
        type: The type of UI part, fixed to 'source'.
        source: The source information.
    """

    type: Literal["source"]
    source: LanguageModelV1Source


class FileUIPart(BaseModel):
    """
    Represents a file part of a message.

    Attributes:
        type: The type of UI part, fixed to 'file'.
        mimeType: The MIME type of the file.
        data: The file data.
    """

    type: Literal["file"]
    mimeType: str
    data: str


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
    ToolInvocationUIPart,
    SourceUIPart,
    FileUIPart,
    StepStartUIPart,
]


# Message and related types
class Message(BaseModel):
    """
    Represents a message in a chat conversation.

    Attributes:
        id: A unique identifier for the message.
        createdAt: Optional timestamp when the message was created.
        experimental_attachments: Optional list of attachments.
        role: The role of the sender (system, user, assistant, or data).
        annotations: Optional list of annotations.
        parts: Optional list of UI parts that make up the message content.
    """

    id: str
    createdAt: Optional[datetime] = None
    content: str  # deprecated, use parts instead
    reasoning: Optional[str] = None  # deprecated, use parts instead
    experimental_attachments: Optional[List[Attachment]] = None
    role: Literal["system", "user", "assistant", "data"]
    # data: Optional[JSONValue] = None
    annotations: Optional[List[JSONValue]] = None
    toolInvocations: Optional[List[ToolInvocation]] = None  # deprecated, use parts instead
    parts: Optional[List[UIPart]] = None


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
