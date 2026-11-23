"""Pydantic-AI agent nodes and events, mapped to the v4 events the stream carries."""

import asyncio
import uuid
from typing import AsyncGenerator, Awaitable, Callable, Iterator

import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)

from core import instrumentation

from chat.ai_sdk_types import SourceUrlUIPart
from chat.clients.pydantic_ui_message_converter import tool_chart
from chat.clients.schema import StreamingState
from chat.llm_configuration import LLModel
from chat.mcp_servers import DataGouvConnector
from chat.turn.trail import TurnTrail
from chat.turn.usage import TokenMeter
from chat.vercel_ai_sdk.core import events_v4

# Not __name__: "chat.turn.*" would nest under the "chat.turn" turn-trace
# logger, whose level and log filter are meant to cover the turn trace alone.
# Keep the name these lines had before the split.
logger = structlog.get_logger("chat.clients.pydantic_ai")

# Stream-protocol contract with the frontend. Mirrored in `useChat.tsx`
# (CONNECTOR_UNAVAILABLE_EVENT_TYPE). Keep both sides in sync.
CONNECTOR_UNAVAILABLE_EVENT_TYPE = "connector_unavailable"


def connector_unavailable_notice() -> events_v4.DataPart:
    """The chat notice for a forced connector this turn could not use."""
    return events_v4.DataPart(
        data=[
            {
                "type": CONNECTOR_UNAVAILABLE_EVENT_TYPE,
                "kind": "chat_notice",
                "connector_id": DataGouvConnector.connector_id,
            }
        ]
    )


class TurnEventMapper:  # pylint: disable=too-many-instance-attributes
    """Walks one agent run's nodes and yields the v4 events they produce.

    One per run. Along the way it writes the turn's text to the trail, charges
    the tokens spent, and collects what finalization needs in `state`.
    """

    def __init__(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        *,
        trail: TurnTrail,
        meter: TokenMeter,
        check_stop: Callable[[], Awaitable[None]],
        model_configuration: LLModel,
        supports_streaming: bool,
        fake_streaming_delay: float,
        datagouv: DataGouvConnector,
    ):
        self._trail = trail
        self._meter = meter
        self._check_stop = check_stop
        self._model_configuration = model_configuration
        self._supports_streaming = supports_streaming
        self._fake_streaming_delay = fake_streaming_delay
        self._datagouv = datagouv
        self.state = StreamingState()

    async def events(self, run) -> AsyncGenerator[events_v4.Event, None]:
        """
        Process nodes from the Pydantic-AI agent iteration loop.

        The agent produces a stream of nodes representing different stages:

        - **UserPromptNode**: The user's input was received (no-op, just logged)
        - **ModelRequestNode**: The model is generating a response
          - Streaming: Yields text/tool deltas as they arrive
          - Non-streaming: Waits for full response, then yields parts
        - **CallToolsNode**: The model requested tool calls
          - Executes tools and yields results
          - Collects source citations into state.ui_sources
        - **EndNode**: The agent run is complete

        This method delegates to specialized handlers for each node type,
        passing the shared StreamingState to track cross-node state.

        The stop check is called for each node to allow cancel between
        processing steps.
        """
        async for node in run:
            await self._check_stop()
            if Agent.is_user_prompt_node(node):
                # A user prompt node => The user has provided input
                pass

            elif Agent.is_model_request_node(node):
                # A model request node => agent is asking the model to generate a response
                async for event in self._handle_model_request_node(node, run.ctx):
                    await self._write_turn_chunks(run, event)
                    yield event

            elif Agent.is_call_tools_node(node):
                # A handle-response node => The model returned some data,
                # potentially calls a tool
                async for event in self._stream_tool_node(node, run.ctx):
                    yield event

    async def _write_turn_chunks(self, run, event) -> None:
        """Append what this event added to the turn: its text, and nothing else.

        The question opened the trail with a snapshot, so there is always a
        request for the answer to belong to, and every structural change takes
        another one of its own (`snapshot_closed_tool_step`). Nothing is
        snapshotted on a timer: a snapshot holds the whole turn, so one every
        few seconds rewrote the answer so far over and over, for a reader that
        only ever uses the last of them.

        What this gives up: only text is appended, so reasoning (`ReasoningPart`,
        from a model with `thinking_tags`) reaches no row of its own. A turn cut
        short while the model is still thinking therefore stores its question
        and nothing else, and the conversation shows that question with no
        answer against it. Giving reasoning the same treatment as text means a
        row that says which of the two it carries, not a timer: that would put
        it back in the trail without snapshotting the whole turn again.
        """
        # Charged as the turn spends them, alongside the rows that record it:
        # a turn that never lands spent its tokens all the same, and would
        # otherwise escape the cooldown entirely.
        await self._meter.charge_run(run)
        if isinstance(event, events_v4.TextPart):
            await self._trail.append_text(event.text)

    async def _handle_non_streaming_response(self, node, run_ctx):
        """Run a model node without streaming, emitting its parts as events."""
        result = await node.run(run_ctx)
        for part in result.model_response.parts:
            if isinstance(part, TextPart):
                if self._fake_streaming_delay:
                    for i in range(0, len(part.content), 4):
                        await self._check_stop()
                        yield events_v4.TextPart(text=part.content[i : i + 4])
                        await asyncio.sleep(self._fake_streaming_delay)
                else:
                    yield events_v4.TextPart(text=part.content)
            elif isinstance(part, ToolCallPart):
                yield events_v4.ToolCallPart(
                    tool_call_id=part.tool_call_id,
                    tool_name=part.tool_name,
                    args=part.args_as_dict(),
                )
            elif isinstance(part, ThinkingPart):
                yield events_v4.ReasoningPart(reasoning=part.content)
            else:
                logger.warning("unknown_part_type", part_type=type(part).__name__)

    async def _handle_streaming_response(self, node, run_ctx):
        """Stream a model node, emitting text/tool/reasoning deltas as events.

        The stream is held on the trail while the node runs: it carries the
        response Pydantic AI is building, which is what a snapshot chunk
        stores for the part of the turn not yet closed.
        """
        observe = instrumentation.streamed_model_request(self._model_configuration)
        async with node.stream(run_ctx) as request_stream:
            self._trail.active_stream = request_stream
            try:
                async for event in observe(request_stream):
                    await self._check_stop()
                    if isinstance(event, PartStartEvent):
                        if isinstance(event.part, TextPart):
                            yield events_v4.TextPart(text=event.part.content)
                        elif isinstance(event.part, ToolCallPart):
                            yield events_v4.ToolCallStreamingStartPart(
                                tool_call_id=event.part.tool_call_id,
                                tool_name=event.part.tool_name,
                            )
                        elif isinstance(event.part, ThinkingPart):
                            yield events_v4.ReasoningPart(reasoning=event.part.content)
                    elif isinstance(event, PartDeltaEvent):
                        if isinstance(event.delta, TextPartDelta):
                            yield events_v4.TextPart(text=event.delta.content_delta)
                        elif isinstance(event.delta, ToolCallPartDelta):
                            self.state.tool_is_streaming = True
                            yield events_v4.ToolCallDeltaPart(
                                tool_call_id=event.delta.tool_call_id,
                                args_text_delta=event.delta.args_delta,
                            )
                        elif isinstance(event.delta, ThinkingPartDelta):
                            yield events_v4.ReasoningPart(reasoning=event.delta.content_delta)
            finally:
                self._trail.active_stream = None

    async def _handle_model_request_node(
        self, node, run_ctx
    ) -> AsyncGenerator[events_v4.Event, None]:
        """Handle model request node - streaming or non-streaming."""
        self.state.tool_is_streaming = False
        if not self._supports_streaming:
            async for event in self._handle_non_streaming_response(node, run_ctx):
                yield event
        else:
            async for event in self._handle_streaming_response(node, run_ctx):
                yield event

    async def _handle_call_tools_node(self, node, run_ctx) -> AsyncGenerator[events_v4.Event, None]:
        """Stream a tool-call node, emitting tool result/error events."""
        async with node.stream(run_ctx) as handle_stream:
            async for event in handle_stream:
                await self._check_stop()
                logger.debug("request_stream_event", event_type=type(event).__name__)
                if isinstance(event, FunctionToolCallEvent):
                    if not self.state.tool_is_streaming:
                        yield events_v4.ToolCallPart(
                            tool_call_id=event.tool_call_id,
                            tool_name=event.part.tool_name,
                            args=event.part.args_as_dict(),
                        )
                elif isinstance(event, FunctionToolResultEvent):
                    for result_event in self._tool_result_events(event):
                        yield result_event

    def _tool_result_events(self, event: FunctionToolResultEvent) -> Iterator[events_v4.Event]:
        """The events for one tool result: outage notice, sources, then the result."""
        # An outage reaches the model as a failed ToolReturnPart.
        if self._datagouv.take_outage():
            yield connector_unavailable_notice()
        if isinstance(event.part, ToolReturnPart):
            if event.part.metadata and (sources := event.part.metadata.get("sources")):
                for source_url in sources:
                    source_id = str(uuid.uuid4())
                    self.state.ui_sources.append(
                        SourceUrlUIPart(type="source-url", sourceId=source_id, url=source_url)
                    )
                    yield events_v4.SourcePart(id=source_id, url=source_url)
            # The UI gets the chart instead of the text the model reads.
            chart = tool_chart(event.part)
            yield events_v4.ToolResultPart(
                tool_call_id=event.tool_call_id,
                result={"chart": chart} if chart else event.part.content,
            )

        elif isinstance(event.part, RetryPromptPart):
            yield events_v4.ToolResultPart(
                tool_call_id=event.tool_call_id, result=event.part.content
            )
        else:
            logger.warning("unexpected_tool_result_type", part_type=type(event.part).__name__)

    async def _stream_tool_node(self, node, run_ctx) -> AsyncGenerator[events_v4.Event, None]:
        """Stream a tool-call node, noting that its step owes a snapshot.

        A tool call is structure rather than more of the same text, and only a
        snapshot carries structure. The snapshot itself waits: Pydantic AI adds
        the tool's return to the run when the next model request starts, so
        taking it here would store a call with no answer, which no provider will
        replay.
        """
        async for event in self._handle_call_tools_node(node, run_ctx):
            yield event
            if isinstance(event, (events_v4.ToolCallPart, events_v4.ToolResultPart)):
                self._trail.note_tool_step()
