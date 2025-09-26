"""
This module contains the event types for the Vercel AI SDK Python SDK.
"""

import json
from enum import StrEnum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import Field

from ...ai_sdk_types import JSONValue
from .types import ConfiguredBaseModel


class EventType(StrEnum):
    """
    The type of event.

    See: https://v4.ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
    """

    TEXT = "0"
    REASONING = "g"
    REDACTED_REASONING = "i"
    REASONING_SIGNATURE = "j"
    SOURCE = "h"
    FILE = "k"
    DATA = "2"
    MESSAGE_ANNOTATION = "8"
    ERROR = "3"
    TOOL_CALL_STREAMING_START = "b"
    TOOL_CALL_DELTA = "c"
    TOOL_CALL = "9"
    TOOL_RESULT = "a"
    START_STEP = "f"
    FINISH_STEP = "e"
    FINISH_MESSAGE = "d"


class BaseEvent(ConfiguredBaseModel):
    """
    Base event for all events in the Vercel AI SDK.
    """

    type: EventType
    # raw_event: Optional[Any] = None


class TextPart(BaseEvent):
    """
    Event for text parts that are appended to the message as they are received.
    """

    type: Literal[EventType.TEXT] = EventType.TEXT
    text: str

    def model_dump_json(self, *args, **kwargs) -> str:
        """
        Override to ensure the text is serialized correctly.
        """
        return json.dumps(self.text)


class ReasoningPart(BaseEvent):
    """
    Event for reasoning parts that are appended to the message as they are received.
    """

    type: Literal[EventType.REASONING] = EventType.REASONING
    reasoning: str

    def model_dump_json(self, *args, **kwargs) -> str:
        return json.dumps(self.reasoning)


class RedactedReasoningPart(BaseEvent):
    """
    Event for redacted reasoning parts.
    """

    type: Literal[EventType.REDACTED_REASONING] = EventType.REDACTED_REASONING
    data: str


class ReasoningSignaturePart(BaseEvent):
    """
    Event for reasoning signature parts.
    """

    type: Literal[EventType.REASONING_SIGNATURE] = EventType.REASONING_SIGNATURE
    signature: str


class SourcePart(BaseEvent):
    """
    Event for source parts.
    """

    type: Literal[EventType.SOURCE] = EventType.SOURCE
    sourceType: Literal["url"] = "url"
    id: str
    url: str
    title: Optional[str] = None
    providerMetadata: Optional[Dict[str, Any]] = None


class FilePart(BaseEvent):
    """
    Event for file parts.
    """

    type: Literal[EventType.FILE] = EventType.FILE
    data: str
    mime_type: str


class DataPart(BaseEvent):
    """
    Event for custom data parts to allow streaming of arbitrary structured data.
    """

    type: Literal[EventType.DATA] = EventType.DATA
    data: List[JSONValue]

    def model_dump_json(self, *args, **kwargs) -> str:
        return json.dumps(self.data)


class MessageAnnotationPart(BaseEvent):
    """
    Event for message annotation parts.
    """

    type: Literal[EventType.MESSAGE_ANNOTATION] = EventType.MESSAGE_ANNOTATION
    annotations: List[JSONValue]

    def model_dump_json(self, *args, **kwargs) -> str:
        return json.dumps(self.data)


class ErrorPart(BaseEvent):
    """
    Event for errors that are appended to the message as they are received.
    """

    type: Literal[EventType.ERROR] = EventType.ERROR
    error: str

    def model_dump_json(self, *args, **kwargs) -> str:
        return json.dumps(self.error)


class ToolCallStreamingStartPart(BaseEvent):
    """
    Event indicating the start of a streaming tool call.
    """

    type: Literal[EventType.TOOL_CALL_STREAMING_START] = EventType.TOOL_CALL_STREAMING_START
    tool_call_id: str
    tool_name: str


class ToolCallDeltaPart(BaseEvent):
    """
    Event representing a delta update for a streaming tool call.
    """

    type: Literal[EventType.TOOL_CALL_DELTA] = EventType.TOOL_CALL_DELTA
    tool_call_id: str
    args_text_delta: str


class ToolCallPart(BaseEvent):
    """
    Event representing a tool call.
    """

    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    tool_call_id: str
    tool_name: str
    args: Dict[str, Any]


class ToolResultPart(BaseEvent):
    """
    Event representing a tool result.
    """

    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT
    tool_call_id: str
    result: Any


class StartStepPart(BaseEvent):
    """
    Event indicating the start of a step.
    """

    type: Literal[EventType.START_STEP] = EventType.START_STEP
    message_id: str


class FinishReason(StrEnum):
    """
    The reason for finishing a step or message.
    """

    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content-filter"
    TOOL_CALLS = "tool-calls"
    ERROR = "error"
    OTHER = "other"
    UNKNOWN = "unknown"


class Usage(ConfiguredBaseModel):
    """
    Token usage information.
    """

    prompt_tokens: int
    completion_tokens: int


class FinishStepPart(BaseEvent):
    """
    Event indicating that a step has been completed.
    """

    type: Literal[EventType.FINISH_STEP] = EventType.FINISH_STEP
    finish_reason: FinishReason
    usage: Usage
    is_continued: bool


class FinishMessagePart(BaseEvent):
    """
    Event indicating the completion of a message with additional metadata.
    """

    type: Literal[EventType.FINISH_MESSAGE] = EventType.FINISH_MESSAGE
    finish_reason: FinishReason
    usage: Usage


Event = Annotated[
    Union[
        TextPart,
        ReasoningPart,
        RedactedReasoningPart,
        ReasoningSignaturePart,
        SourcePart,
        FilePart,
        DataPart,
        MessageAnnotationPart,
        ErrorPart,
        ToolCallStreamingStartPart,
        ToolCallDeltaPart,
        ToolCallPart,
        ToolResultPart,
        StartStepPart,
        FinishStepPart,
        FinishMessagePart,
    ],
    Field(discriminator="type"),
]
