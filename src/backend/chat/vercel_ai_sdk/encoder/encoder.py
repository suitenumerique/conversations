"""Event Encoder for Vercel AI SDK"""

from enum import Enum
from typing import Union

from ..core.events_v4 import BaseEvent as V4BaseEvent
from ..core.events_v4 import TextPart
from ..core.events_v5 import BaseEvent as V5BaseEvent
from ..core.events_v5 import TextDeltaEvent


class EventEncoderVersion(str, Enum):
    """Enumeration of supported event encoder versions."""

    V4 = "v4"
    V5 = "v5"


CURRENT_EVENT_ENCODER_VERSION = EventEncoderVersion.V4  # used encoder version


class EventEncoder:
    """
    Encodes events for the Vercel AI SDK based on the specified version.
    """

    def __init__(self, version: EventEncoderVersion):
        """
        Initializes the EventEncoder with the specified version.
        """
        if version not in [EventEncoderVersion.V4, EventEncoderVersion.V5]:
            raise ValueError("Unsupported version. Supported versions are 'v4' and 'v5'.")

        self.version = version

    def get_content_type(self) -> str:
        """
        Returns the content type of the encoder.
        """
        return "text/event-stream"

    def encode(self, event: Union[V4BaseEvent, V5BaseEvent]) -> str | None:
        """
        Encodes an event based on the version.

        Args:
            event (Union[V5BaseEvent, V4BaseEvent]): The event to encode.
        Returns:
            str | None: The encoded event as a string,
            or None if the event type is not adapted to the SDK version.
        """
        if self.version == EventEncoderVersion.V4 and isinstance(event, V4BaseEvent):
            return self._encode_v4_streaming(event)

        if self.version == EventEncoderVersion.V5 and isinstance(event, V5BaseEvent):
            return self._encode_sse(event)

        return None

    def encode_text(self, event: Union[V4BaseEvent, V5BaseEvent]) -> str | None:
        """
        Encodes an event based on the version.

        Args:
            event (Union[V5BaseEvent, V4BaseEvent]): The event to encode.
        Returns:
            str | None: The encoded event as a string,
            or None if the event type is not adapted to the SDK version.
        """
        if self.version == EventEncoderVersion.V4 and isinstance(event, TextPart):
            return event.text

        if self.version == EventEncoderVersion.V5 and isinstance(event, TextDeltaEvent):
            return event.delta

        return None

    def _encode_v4_streaming(self, event: V4BaseEvent) -> str:
        """
        Encodes an event into a V4 streaming format string.
        """
        return f"{event.type}:{event.model_dump_json(by_alias=True, exclude={'type'})}\n"

    def _encode_sse(self, event: Union[V4BaseEvent, V5BaseEvent]) -> str:
        """
        Encodes an event into an SSE string.
        """
        return f"data: {event.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
