"""
This module contains the event types for the Vercel AI SDK Python SDK.
"""

from enum import Enum
from typing import Annotated, Any, Dict, Literal, Union

from pydantic import Field

from .types import ConfiguredBaseModel


class EventType(str, Enum):
    """
    The type of event.
    """

    MESSAGE_START = "start"
    TEXT_START = "text-start"
    TEXT_DELTA = "text-delta"
    TEXT_END = "text-end"
    REASONING_START = "reasoning-start"
    REASONING_DELTA = "reasoning-delta"
    REASONING_END = "reasoning-end"
    SOURCE_URL = "source-url"
    SOURCE_DOCUMENT = "source-document"
    FILE = "file"
    DATA = "data"
    ERROR = "error"
    TOOL_INPUT_START = "tool-input-start"
    TOOL_INPUT_DELTA = "tool-input-delta"
    TOOL_INPUT_AVAILABLE = "tool-input-available"
    TOOL_OUTPUT_AVAILABLE = "tool-output-available"
    START_STEP = "start-step"
    FINISH_STEP = "finish-step"
    FINISH_MESSAGE = "finish"


class BaseEvent(ConfiguredBaseModel):
    """
    Base event for all events in the Vercel AI SDK.
    """

    type: EventType


class MessageStartEvent(BaseEvent):
    """
    Event indicating the start of a new message with metadata.
    """

    type: Literal[EventType.MESSAGE_START] = EventType.MESSAGE_START
    messageId: str


class TextStartEvent(BaseEvent):
    """
    Event indicating the beginning of a text block.
    """

    type: Literal[EventType.TEXT_START] = EventType.TEXT_START
    id: str


class TextDeltaEvent(BaseEvent):
    """
    Event containing incremental text content for the text block.
    """

    type: Literal[EventType.TEXT_DELTA] = EventType.TEXT_DELTA
    id: str
    delta: str


class TextEndEvent(BaseEvent):
    """
    Event indicating the completion of a text block.
    """

    type: Literal[EventType.TEXT_END] = EventType.TEXT_END
    id: str


class ReasoningStartEvent(BaseEvent):
    """
    Event indicating the beginning of a reasoning block.
    """

    type: Literal[EventType.REASONING_START] = EventType.REASONING_START
    id: str


class ReasoningDeltaEvent(BaseEvent):
    """
    Event containing incremental reasoning content for the reasoning block.
    """

    type: Literal[EventType.REASONING_DELTA] = EventType.REASONING_DELTA
    id: str
    delta: str


class ReasoningEndEvent(BaseEvent):
    """
    Event indicating the completion of a reasoning block.
    """

    type: Literal[EventType.REASONING_END] = EventType.REASONING_END
    id: str


class SourceUrlPart(BaseEvent):
    """
    Event for references to external URLs.
    """

    type: Literal[EventType.SOURCE_URL] = EventType.SOURCE_URL
    sourceId: str
    url: str


class SourceDocumentPart(BaseEvent):
    """
    Event for references to documents or files.
    """

    type: Literal[EventType.SOURCE_DOCUMENT] = EventType.SOURCE_DOCUMENT
    sourceId: str
    mediaType: str
    title: str


class FilePart(BaseEvent):
    """
    Event for references to files with their media type.
    """

    type: Literal[EventType.FILE] = EventType.FILE
    url: str
    mediaType: str


class DataPart(BaseEvent):
    """
    Event for custom data parts to allow streaming of arbitrary structured data.
    """

    type: Literal[EventType.DATA] = EventType.DATA
    data: Dict[str, Any]


class ErrorPart(BaseEvent):
    """
    Event for errors that are appended to the message as they are received.
    """

    type: Literal[EventType.ERROR] = EventType.ERROR
    errorText: str


class ToolInputStartPart(BaseEvent):
    """
    Event indicating the beginning of tool input streaming.
    """

    type: Literal[EventType.TOOL_INPUT_START] = EventType.TOOL_INPUT_START
    toolCallId: str
    toolName: str


class ToolInputDeltaPart(BaseEvent):
    """
    Event for incremental chunks of tool input as it's being generated.
    """

    type: Literal[EventType.TOOL_INPUT_DELTA] = EventType.TOOL_INPUT_DELTA
    toolCallId: str
    inputTextDelta: str


class ToolInputAvailablePart(BaseEvent):
    """
    Event indicating that tool input is complete and ready for execution.
    """

    type: Literal[EventType.TOOL_INPUT_AVAILABLE] = EventType.TOOL_INPUT_AVAILABLE
    toolCallId: str
    toolName: str
    input: Dict[str, Any]


class ToolOutputAvailablePart(BaseEvent):
    """
    Event containing the result of tool execution.
    """

    type: Literal[EventType.TOOL_OUTPUT_AVAILABLE] = EventType.TOOL_OUTPUT_AVAILABLE
    toolCallId: str
    output: Dict[str, Any]


class StartStepPart(BaseEvent):
    """
    Event indicating the start of a step.
    """

    type: Literal[EventType.START_STEP] = EventType.START_STEP


class FinishStepPart(BaseEvent):
    """
    Event indicating that a step has been completed.
    """

    type: Literal[EventType.FINISH_STEP] = EventType.FINISH_STEP


class FinishMessagePart(BaseEvent):
    """
    Event indicating the completion of a message.
    """

    type: Literal[EventType.FINISH_MESSAGE] = EventType.FINISH_MESSAGE


Event = Annotated[
    Union[
        MessageStartEvent,
        TextStartEvent,
        TextDeltaEvent,
        TextEndEvent,
        ReasoningStartEvent,
        ReasoningDeltaEvent,
        ReasoningEndEvent,
        SourceUrlPart,
        SourceDocumentPart,
        FilePart,
        DataPart,
        ErrorPart,
        ToolInputStartPart,
        ToolInputDeltaPart,
        ToolInputAvailablePart,
        ToolOutputAvailablePart,
        StartStepPart,
        FinishStepPart,
        FinishMessagePart,
    ],
    Field(discriminator="type"),
]
