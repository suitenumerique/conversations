"""
This module contains the event types for the Vercel AI SDK Python SDK.
"""

from enum import Enum
from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import Field, field_validator

from .types import ConfiguredBaseModel

# Named data parts are typed ``data-<name>`` on the wire; a bare ``data`` type is
# not routed to the client's ``onData`` callback.
DATA_TYPE_PREFIX = "data-"


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
    messageId: Optional[str] = None


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
    title: Optional[str] = None


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

    The wire type carries the part name (``data-cooldown``, ``data-keepalive``...);
    only such named parts reach the client's ``onData`` callback. ``transient``
    parts are delivered to ``onData`` only and never appended to the message,
    which is what every part we emit wants: they are all consumed at stream time.
    """

    type: str
    data: Dict[str, Any]
    transient: bool = True

    @field_validator("type")
    @classmethod
    def _check_named(cls, value: str) -> str:
        """Reject a bare ``data`` type, which the client would silently drop."""
        if not value.startswith(DATA_TYPE_PREFIX) or value == DATA_TYPE_PREFIX:
            raise ValueError(f"Data part type must be '{DATA_TYPE_PREFIX}<name>', got {value!r}")
        return value


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
    # Tool results are not always objects: the agent yields plain strings and
    # lists too, so the payload stays untyped.
    output: Any


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

    ``messageMetadata`` is surfaced by the client as ``message.metadata``; it is
    how per-message usage and CO2 impact reach the UI.
    """

    type: Literal[EventType.FINISH_MESSAGE] = EventType.FINISH_MESSAGE
    messageMetadata: Optional[Dict[str, Any]] = None


# ``DataPart`` stays out of the discriminated union: its type is dynamic
# (``data-<name>``), so it cannot act as a discriminator literal.
Event = Union[
    Annotated[
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
    ],
    DataPart,
]
