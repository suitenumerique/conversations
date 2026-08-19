"""Translate the agent's v4 stream events into v5 UI-message-stream chunks.

The agent (``chat/clients/pydantic_ai.py``) emits v4 events exclusively. Rather
than rewriting every emit site, the wire upgrade happens here, at the encoding
boundary: feed one v4 event in, get the v5 chunks it becomes out.

The translation is stateful for two reasons:

* v5 text and reasoning are *blocks* (``text-start`` / ``text-delta`` /
  ``text-end``) while v4 streams bare deltas, so the translator opens a block on
  the first delta and closes it when anything else arrives;
* v4 message annotations are a separate frame while v5 carries them as
  ``messageMetadata`` on ``finish``, so annotations are buffered until then.

One instance per stream.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..core import events_v4, events_v5

logger = logging.getLogger(__name__)

TEXT_BLOCK = "text"
REASONING_BLOCK = "reasoning"

# start/delta/end event classes per block kind.
_BLOCK_EVENTS = {
    TEXT_BLOCK: (
        events_v5.TextStartEvent,
        events_v5.TextDeltaEvent,
        events_v5.TextEndEvent,
    ),
    REASONING_BLOCK: (
        events_v5.ReasoningStartEvent,
        events_v5.ReasoningDeltaEvent,
        events_v5.ReasoningEndEvent,
    ),
}


def data_part_type(name: str) -> str:
    """Build the wire type of a named data part, e.g. ``keep_alive`` -> ``data-keep-alive``."""
    return f"{events_v5.DATA_TYPE_PREFIX}{name.replace('_', '-')}"


class V4ToV5Translator:
    """Turn a stream of v4 events into the equivalent v5 chunks."""

    def __init__(self) -> None:
        self._open_block: Optional[Tuple[str, str]] = None
        self._block_count = 0
        self._annotations: Dict[str, Any] = {}

    def translate(self, event: events_v4.Event) -> List[events_v5.Event]:
        """Translate a single v4 event into the v5 chunks it becomes."""
        if isinstance(event, events_v4.TextPart):
            return self._delta(TEXT_BLOCK, event.text)

        if isinstance(event, events_v4.ReasoningPart):
            return self._delta(REASONING_BLOCK, event.reasoning)

        if isinstance(event, events_v4.MessageAnnotationPart):
            # Buffered, not emitted: v5 delivers annotations as `finish` metadata.
            for annotation in event.annotations:
                if isinstance(annotation, dict):
                    self._annotations.update(annotation)
                else:
                    logger.warning("Dropping non-object message annotation: %r", annotation)
            return []

        return self._close_block() + self._translate_standalone(event)

    def flush(self) -> List[events_v5.Event]:
        """Close whatever is still open at the end of the stream."""
        return self._close_block()

    def _translate_standalone(  # noqa: PLR0911  # pylint: disable=too-many-return-statements
        self, event: events_v4.Event
    ) -> List[events_v5.Event]:
        """Translate an event that is not part of a text or reasoning block."""
        if isinstance(event, events_v4.ToolCallStreamingStartPart):
            return [
                events_v5.ToolInputStartPart(
                    toolCallId=event.tool_call_id, toolName=event.tool_name
                )
            ]

        if isinstance(event, events_v4.ToolCallDeltaPart):
            return [
                events_v5.ToolInputDeltaPart(
                    toolCallId=event.tool_call_id, inputTextDelta=event.args_text_delta
                )
            ]

        if isinstance(event, events_v4.ToolCallPart):
            return [
                events_v5.ToolInputAvailablePart(
                    toolCallId=event.tool_call_id,
                    toolName=event.tool_name,
                    input=event.args,
                )
            ]

        if isinstance(event, events_v4.ToolResultPart):
            return [
                events_v5.ToolOutputAvailablePart(
                    toolCallId=event.tool_call_id, output=event.result
                )
            ]

        if isinstance(event, events_v4.SourcePart):
            return [events_v5.SourceUrlPart(sourceId=event.id, url=event.url, title=event.title)]

        if isinstance(event, events_v4.StartStepPart):
            return [events_v5.StartStepPart()]

        if isinstance(event, events_v4.FinishStepPart):
            return [events_v5.FinishStepPart()]

        if isinstance(event, events_v4.DataPart):
            return self._data_parts(event)

        if isinstance(event, events_v4.ErrorPart):
            # The frontend keys its error handling on these codes.
            return [events_v5.ErrorPart(errorText=event.error)]

        if isinstance(event, events_v4.FinishMessagePart):
            return [events_v5.FinishMessagePart(messageMetadata=self._message_metadata(event))]

        logger.warning("No v5 translation for v4 event type %s", type(event).__name__)
        return []

    @staticmethod
    def _data_parts(event: events_v4.DataPart) -> List[events_v5.Event]:
        """Split a v4 data frame into one named, transient v5 data part per item.

        Every data part we emit is consumed while the stream runs (title,
        cooldown, skipped images, keep-alive), so none of them belong in the
        persisted message: `transient` delivers them to `onData` only.
        """
        parts = []
        for item in event.data:
            # An empty type must be dropped here too: `data_part_type("")` yields
            # a bare `data-`, which the v5 DataPart validator rejects outright.
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("type"), str)
                or not item["type"]
            ):
                logger.warning("Dropping data item without a string type: %r", item)
                continue
            parts.append(
                events_v5.DataPart(type=data_part_type(item["type"]), data=item, transient=True)
            )
        return parts

    def _message_metadata(self, event: events_v4.FinishMessagePart) -> Dict[str, Any]:
        """Build the `finish` metadata from the buffered annotations and the usage."""
        return {
            "usage": event.usage.model_dump(by_alias=True, exclude_none=True),
            **self._annotations,
        }

    def _delta(self, kind: str, delta: str) -> List[events_v5.Event]:
        """Emit a delta, opening the matching block first when needed."""
        events: List[events_v5.Event] = []
        if self._open_block is None or self._open_block[0] != kind:
            events += self._close_block()
            block_id = str(self._block_count)
            self._block_count += 1
            self._open_block = (kind, block_id)
            events.append(_BLOCK_EVENTS[kind][0](id=block_id))
        events.append(_BLOCK_EVENTS[kind][1](id=self._open_block[1], delta=delta))
        return events

    def _close_block(self) -> List[events_v5.Event]:
        """Close the open text or reasoning block, if any."""
        if self._open_block is None:
            return []
        kind, block_id = self._open_block
        self._open_block = None
        return [_BLOCK_EVENTS[kind][2](id=block_id)]
