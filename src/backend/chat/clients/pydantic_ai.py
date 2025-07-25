"""
Pydantic-AI based AIAgentService.

This file replaces the previous OpenAI-specific client with a Pydantic-AI
implementation while keeping the *exact* same public API so that no
changes are needed in views.py or tests.
"""

import dataclasses
import json
import logging
from contextlib import AsyncExitStack
from itertools import chain
from typing import Dict, List

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from asgiref.sync import sync_to_async
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
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
from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from chat.ai_sdk_types import (
    UIMessage,
)
from chat.clients.async_to_sync import convert_async_generator_to_sync
from chat.clients.pydantic_ui_message_converter import (
    model_message_to_ui_message,
    ui_message_to_model_message,
    ui_message_to_user_content,
)
from chat.mcp_servers import get_mcp_servers
from chat.tools import get_pydantic_tools_by_name

logger = logging.getLogger(__name__)


def _build_pydantic_agent(mcp_servers) -> Agent[None, str]:
    """Create a Pydantic AI Agent instance with the configured settings."""
    if settings.AI_BASE_URL is None or settings.AI_API_KEY is None or settings.AI_MODEL is None:
        raise ImproperlyConfigured("AIChatService configuration not set")

    agent = Agent(
        model=OpenAIModel(
            model_name=settings.AI_MODEL,
            provider=OpenAIProvider(
                base_url=settings.AI_BASE_URL,
                api_key=settings.AI_API_KEY,
            ),
            settings=OpenAIResponsesModelSettings(
                openai_reasoning_effort="low",
                openai_reasoning_summary="detailed",
            ),
        ),
        system_prompt=settings.AI_AGENT_INSTRUCTIONS,
        mcp_servers=mcp_servers,
        tools=[get_pydantic_tools_by_name(tool_name) for tool_name in settings.AI_AGENT_TOOLS],
    )

    return agent


class AIAgentService:
    """Service class for AI-related operations (Pydantic-AI edition)."""

    def __init__(self, conversation):
        self.conversation = conversation

    # --------------------------------------------------------------------- #
    # Public streaming API (unchanged signatures)
    # --------------------------------------------------------------------- #

    def stream_text(self, messages: List[UIMessage]):
        """Return only the assistant text deltas (legacy text mode)."""
        return convert_async_generator_to_sync(self.stream_text_async(messages))

    def stream_data(self, messages: List[UIMessage]):
        """Return Vercel-AI-SDK formatted events."""
        return convert_async_generator_to_sync(self.stream_data_async(messages))

    # --------------------------------------------------------------------- #
    # Async internals
    # --------------------------------------------------------------------- #

    async def stream_text_async(self, messages: List[UIMessage]):
        """Return only the assistant text deltas (legacy text mode)."""
        async for delta in self._run_agent(messages):
            if delta["type"] == "0":
                yield delta["payload"]

    async def stream_data_async(self, messages: List[UIMessage]):
        """Return Vercel-AI-SDK formatted events."""
        async for delta in self._run_agent(messages):
            yield f"{delta['type']}:{json.dumps(delta['payload'])}\n"

    # --------------------------------------------------------------------- #
    # Core agent runner
    # --------------------------------------------------------------------- #

    # pylint: disable=too-many-branches,too-many-statements
    async def _run_agent(self, messages: List[UIMessage]):  # noqa: PLR0912
        """Run the Pydantic AI agent and stream events."""
        if messages[-1].role != "user":
            return

        history = [ui_message_to_model_message(message) for message in messages[:-1]]
        prompt = ui_message_to_user_content(messages[-1])
        usage = {"promptTokens": 0, "completionTokens": 0}

        async with AsyncExitStack() as stack:
            # MCP servers (if any) can be initialized here
            mcp_servers = [await stack.enter_async_context(mcp) for mcp in get_mcp_servers()]

            async with _build_pydantic_agent(mcp_servers).iter(
                prompt, message_history=history
            ) as run:
                async for node in run:
                    if Agent.is_user_prompt_node(node):
                        # A user prompt node => The user has provided input
                        pass

                    elif Agent.is_model_request_node(node):
                        # A model request node => We can stream tokens from the model's request
                        async with node.stream(run.ctx) as request_stream:
                            async for event in request_stream:
                                logger.debug("Received request_stream event: %s", type(event))
                                if isinstance(event, PartStartEvent):
                                    logger.debug("PartStartEvent: %s", dataclasses.asdict(event))

                                    if isinstance(event.part, TextPart):
                                        yield {"type": "0", "payload": event.part.content}
                                    elif isinstance(event.part, ToolCallPart):
                                        yield {
                                            "type": "b",
                                            "payload": {
                                                "toolCallId": event.part.tool_call_id,
                                                "toolName": event.part.tool_name,
                                            },
                                        }
                                    elif isinstance(event.part, ThinkingPart):
                                        yield {"type": "g", "payload": event.part.content}

                                elif isinstance(event, PartDeltaEvent):
                                    logger.debug(
                                        "PartDeltaEvent: %s %s",
                                        type(event),
                                        dataclasses.asdict(event),
                                    )
                                    if isinstance(event.delta, TextPartDelta):
                                        yield {"type": "0", "payload": event.delta.content_delta}
                                    elif isinstance(event.delta, ToolCallPartDelta):
                                        yield {
                                            "type": "c",
                                            "payload": {
                                                "toolCallId": event.delta.tool_call_id,
                                                "argsTextDelta": event.delta.args_delta,
                                            },
                                        }
                                    elif isinstance(event.delta, ThinkingPartDelta):
                                        yield {"type": "g", "payload": event.delta.content_delta}

                    elif Agent.is_call_tools_node(node):
                        # A handle-response node => The model returned some data,
                        # potentially calls a tool
                        async with node.stream(run.ctx) as handle_stream:
                            async for event in handle_stream:
                                logger.debug(
                                    "Received request_stream event: %s, %s",
                                    type(event),
                                    dataclasses.asdict(event),
                                )
                                if isinstance(event, FunctionToolCallEvent):
                                    # We are already streaming the tool call events don't yield
                                    # the tool call again
                                    pass
                                    # yield {
                                    #    "type": "9",
                                    #    "payload": {
                                    #         "toolCallId": event.part.tool_call_id,
                                    #         "toolName": event.part.tool_name,
                                    #        "args": event.part.args,
                                    #    },
                                    # }
                                elif isinstance(event, FunctionToolResultEvent):
                                    if isinstance(event.result, ToolReturnPart):
                                        yield {
                                            "type": "a",
                                            "payload": {
                                                "toolCallId": event.tool_call_id,
                                                "result": event.result.content,
                                            },
                                        }
                                    elif isinstance(event.result, RetryPromptPart):
                                        yield {
                                            "type": "a",
                                            "payload": {
                                                "toolCallId": event.tool_call_id,
                                                "result": event.result.content,
                                            },
                                        }
                                    else:
                                        logger.warning(
                                            "Unexpected tool result type: %s %s",
                                            type(event.result),
                                            dataclasses.asdict(event.result),
                                        )
                    elif Agent.is_end_node(node):
                        # Once an End node is reached, the agent run is complete
                        logger.debug("Received end_node event: %s", dataclasses.asdict(node))
                    else:
                        logger.warning(
                            "Unknown node type encountered: %s",
                            type(node),
                        )

                # Final usage summary
                final_usage = run.usage()
                usage["promptTokens"] = final_usage.request_tokens
                usage["completionTokens"] = final_usage.response_tokens

        # Persist conversation
        await sync_to_async(self._update_conversation)(
            history, run.result.new_messages(), run.result.new_messages_json(), usage
        )

        # Vercel finish message
        yield {
            "type": "d",
            "payload": {
                "finishReason": "stop",
                "usage": usage,
            },
        }

    def _update_conversation(
        self,
        history: List[ModelMessage],
        final_output: List[ModelRequest | ModelMessage],
        raw_final_output: bytes,
        usage: Dict[str, int],
    ):
        """Persist messages + usage to DB (simplified)."""
        _merged_final_output_request = None
        _merged_final_output_message = None

        _merged_final_output_request = ModelRequest(
            parts=[
                part for msg in final_output if isinstance(msg, ModelRequest) for part in msg.parts
            ],
            kind="request",
        )
        _merged_final_output_message = ModelResponse(
            parts=[
                part for msg in final_output if isinstance(msg, ModelResponse) for part in msg.parts
            ],
            kind="response",
        )

        self.conversation.messages = [
            model_message_to_ui_message(msg)
            for msg in chain(history, [_merged_final_output_request, _merged_final_output_message])
        ]
        for message in self.conversation.messages:
            logger.debug("conversation.messages: %s %s", type(message), message)
        self.conversation.messages = [
            msg.model_dump(mode="json") for msg in self.conversation.messages if msg
        ]
        self.conversation.agent_usage = usage

        logger.debug(
            "raw_final_output: %s %s",
            raw_final_output.decode("utf-8"),
            json.loads(raw_final_output.decode("utf-8")),
        )
        self.conversation.openai_messages += json.loads(raw_final_output.decode("utf-8"))

        self.conversation.save()
