"""AIAgentService class for handling AI agent interactions."""

import asyncio
import json
import logging
import queue
import threading
import uuid
from contextlib import AsyncExitStack
from typing import List

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from agents import Agent, ModelResponse, OpenAIChatCompletionsModel, Runner, Usage
from asgiref.sync import sync_to_async
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputItemParam, ResponseOutputItem
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
    ResponseUsage,
)

from chat.ai_sdk_types import (
    TextUIPart,
    ToolInvocationPartialCall,
    ToolInvocationResult,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.mcp_servers import get_mcp_servers
from chat.tools import agent_get_current_weather

logger = logging.getLogger(__name__)


def convert_async_generator_to_sync(async_gen):
    """Convert an async generator to a sync generator."""
    q = queue.Queue()
    sentinel = object()

    async def run_async_gen():
        try:
            async for item in async_gen:
                q.put(item)
        finally:
            q.put(sentinel)

    def start_async_loop():
        asyncio.run(run_async_gen())

    thread = threading.Thread(target=start_async_loop)
    thread.start()

    while True:
        item = q.get()
        if item is sentinel:
            break
        yield item

    thread.join()


class AIAgentService:
    """Service class for AI-related operations."""

    def __init__(self, conversation):
        """Ensure that the AI configuration is set properly."""
        if settings.AI_BASE_URL is None or settings.AI_API_KEY is None or settings.AI_MODEL is None:
            raise ImproperlyConfigured("AIChatService configuration not set")

        self.model = OpenAIChatCompletionsModel(
            model=settings.AI_MODEL,
            openai_client=AsyncOpenAI(
                base_url=settings.AI_BASE_URL,
                api_key=settings.AI_API_KEY,
            ),
        )
        self.conversation = conversation

    @staticmethod
    def _convert_to_openai_messages(  # noqa: PLR0912
        messages: List[UIMessage],
    ) -> List[ResponseInputItemParam]:
        openai_messages = []

        for message in messages:
            content_parts = []
            tool_calls = []

            for part in message.parts:
                match part.type:
                    case "text":
                        content_parts.append({"type": "input_text", "text": part.text})

                    case "image":
                        content_parts.append(
                            {
                                "type": "input_image",
                                "image_url": part.url,
                            }
                        )

                    case "file":
                        content_parts.append(
                            {
                                "type": "input_file",
                                "file_data": part.url,
                                "filename": part.name,
                            }
                        )

                    case "tool-invocation":
                        # Extract the tool invocation data
                        tool_invocation = part.toolInvocation
                        tool_calls.append(
                            {
                                "call_id": tool_invocation.toolCallId,
                                "type": "function_call",
                                "name": tool_invocation.toolName,
                                "arguments": json.dumps(tool_invocation.args),
                                "status": tool_invocation.state,
                            }
                        )

                    case _:
                        logger.warning("Unrecognized part type: %s in part: %s", part.type, part)

            # Add experimental attachments if they exist
            if hasattr(message, "experimental_attachments") and message.experimental_attachments:
                for attachment in message.experimental_attachments:
                    if attachment.contentType.startswith("image"):
                        content_parts.append(
                            {
                                "type": "input_image",
                                "image_url": attachment.url,
                            }
                        )
                    elif attachment.contentType.startswith("text"):
                        content_parts.append(
                            {
                                "type": "input_file",
                                "file_data": attachment.url,
                                "filename": attachment.name,
                            }
                        )

            # Add tool calls separately
            for tool_call in tool_calls:
                openai_messages.append(tool_call)

            # Add message with content parts if there are any
            if content_parts:
                openai_messages.append({"role": message.role, "content": content_parts})

        return openai_messages

    def stream_text(self, messages: List[UIMessage]):
        """Simple generator to convert async generator to sync generator."""
        async_generator = self.stream_text_async(messages)
        return convert_async_generator_to_sync(async_generator)

    async def stream_text_async(self, messages: List[UIMessage]):
        """Async generator for streaming agent events."""
        openai_messages = self._convert_to_openai_messages(messages)
        logger.info("[stream_data_async] Received messages: %s", openai_messages)

        mcp_servers = get_mcp_servers()

        async with mcp_servers[0] as mcp_server:
            agent = Agent(
                name=settings.AI_AGENT_NAME,
                instructions=settings.settings.AI_AGENT_INSTRUCTIONS,
                model=self.model,
                tools=[agent_get_current_weather],
                mcp_servers=[mcp_server],
            )
            result = Runner.run_streamed(
                agent,
                input=openai_messages,
            )

            async for event in result.stream_events():
                logger.info("[stream_text_async] Received event: %s", event)
                if event.type == "raw_response_event":
                    data = event.data
                    logger.info("[stream_text_async]  - data: %s", data)
                    if data.type == "response.output_text.delta":
                        yield data.delta

            # At the end, save the response and yield the finish message part
            _response_usage = Usage()
            for raw_response in result.raw_responses:
                _response_usage.add(raw_response.usage)

            await sync_to_async(self._update_conversation)(
                openai_messages, result.raw_responses, _response_usage
            )

    def stream_data(self, messages: List[UIMessage]):
        """Simple generator to convert async generator to sync generator."""
        async_generator = self.stream_data_async(messages)
        return convert_async_generator_to_sync(async_generator)

    async def stream_data_async(self, messages: List[UIMessage]):
        """Async generator for streaming agent events."""
        finish_reason = "stop"

        openai_messages = self._convert_to_openai_messages(messages)
        logger.info("[stream_data_async] Received messages: %s", openai_messages)

        async with AsyncExitStack() as stack:
            initialized_mcp_servers = [
                await stack.enter_async_context(mcp_server) for mcp_server in get_mcp_servers()
            ]

            agent = Agent(
                name=settings.AI_AGENT_NAME,
                instructions=settings.AI_AGENT_INSTRUCTIONS,
                model=self.model,
                #tools=[agent_get_current_weather],
                mcp_servers=initialized_mcp_servers,
            )
            result = Runner.run_streamed(
                agent,
                input=openai_messages,
            )

            try:
                async for event in result.stream_events():
                    # logger.info("[stream_data_async] Received event: %s", event)

                    if event.type == "raw_response_event":
                        data = event.data
                        # logger.info("[stream_data_async]   - data: %s", data)
                        if data.type == "response.output_text.delta":
                            yield f"0:{json.dumps(data.delta)}\n"

                        if hasattr(data, "finish_reason") and data.finish_reason:
                            finish_reason = data.finish_reason

                    elif event.type == "run_item_stream_event":
                        item = event.item
                        if item.type == "tool_call_item":
                            _tool_call = {
                                "toolCallId": item.raw_item.call_id,
                                "toolName": item.raw_item.name,
                                "args": (
                                    json.loads(item.raw_item.arguments)
                                    if hasattr(item.raw_item, "arguments")
                                    else {}
                                ),
                            }
                            yield f"9:{json.dumps(_tool_call)}\n"
                        elif item.type == "tool_call_output_item":
                            _tool_call_result = {
                                "toolCallId": str(item.raw_item["call_id"]),
                                "result": item.raw_item["output"],
                            }
                            yield f"a:{json.dumps(_tool_call_result)}\n"
                    elif event.type == "agent_updated_stream_event":
                        logger.info(
                            "[stream_data_async] Agent switched to: %s", event.new_agent.name
                        )

            except Exception as e:  # pylint: disable=broad-except
                logger.exception("Error in stream_data_async")
                yield f"3:{json.dumps(str(e))}\n"
                finish_reason = "error"

            # At the end, save the response and yield the finish message part
            _response_usage = Usage()
            for raw_response in result.raw_responses:
                _response_usage.add(raw_response.usage)

            await sync_to_async(self._update_conversation)(
                openai_messages, result.raw_responses, _response_usage
            )

            _finish_message = {
                "finishReason": finish_reason,
                "usage": {
                    "promptTokens": _response_usage.input_tokens,
                    "completionTokens": _response_usage.output_tokens,
                },
            }
            yield f"d:{json.dumps(_finish_message)}\n"

    def _update_conversation(
        self,
        input_messages: List[ResponseInputItemParam],
        result_raw_responses: List[ModelResponse],
        response_usage: Usage,
    ):
        ui_messages = []

        self.conversation.openai_messages = input_messages + [
            output.model_dump()
            for raw_response in result_raw_responses
            for output in raw_response.output
        ]

        for raw_response in result_raw_responses:
            ui_messages += self._convert_openai_output_to_ui_messages(raw_response.output)

        self.conversation.messages = self.conversation.ui_messages + [
            ui_message.model_dump() for ui_message in ui_messages
        ]

        if self.conversation.agent_usage:
            total_usage = ResponseUsage(**self.conversation.agent_usage)
        else:
            total_usage = ResponseUsage(
                input_tokens=0,
                output_tokens=0,
                input_tokens_details=InputTokensDetails(cached_tokens=0),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
                total_tokens=0,
            )

        total_usage.input_tokens += response_usage.input_tokens  # pylint: disable=no-member
        total_usage.output_tokens += response_usage.output_tokens  # pylint: disable=no-member
        total_usage.input_tokens_details.cached_tokens += (
            response_usage.input_tokens_details.cached_tokens
        )
        total_usage.output_tokens_details.reasoning_tokens += (
            response_usage.output_tokens_details.reasoning_tokens
        )
        total_usage.total_tokens = response_usage.total_tokens

        self.conversation.agent_usage = total_usage.model_dump()

        self.conversation.save()

    def _convert_openai_output_to_ui_messages(
        self, output: List[ResponseOutputItem]
    ) -> List[UIMessage]:
        """Convert OpenAI output to UI messages."""
        ui_messages = []

        for item in output:
            if item.type == "message":
                text_parts = [TextUIPart(type="text", text=item.text) for item in item.content]
                ui_messages.append(
                    UIMessage(
                        id=str(uuid.uuid4()),
                        role="assistant",
                        parts=text_parts,
                        content="".join(part.text for part in text_parts),
                    )
                )
            elif item.type == "function_call":
                if item.status == "in_progress":
                    tool_invocation = ToolInvocationPartialCall(
                        state="partial-call",
                        step=None,
                        toolCallId=item.call_id,
                        toolName=item.name,
                        args=json.loads(item.arguments),
                    )
                elif item.status == "completed":
                    tool_invocation = ToolInvocationResult(
                        state="result",
                        step=None,
                        toolCallId=item.call_id,
                        toolName=item.name,
                        args=json.loads(item.arguments),
                        result=json.loads(item.result) if item.result else None,
                    )
                # elif item.status == "incomplete":
                else:
                    logger.warning("[stream_data_async] Unhandled message: %s", item)
                    continue

                ui_tool_invocation = ToolInvocationUIPart(
                    type="tool-invocation",
                    toolInvocation=tool_invocation,
                )
                ui_messages.append(UIMessage(role="assistant", parts=[ui_tool_invocation]))
            # Handle other types as needed
        return ui_messages
