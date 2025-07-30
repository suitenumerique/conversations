"""
Pydantic-AI based AIAgentService.

This file replaces the previous OpenAI-specific client with a Pydantic-AI
implementation while keeping the *exact* same public API so that no
changes are needed in views.py or tests.
"""

import dataclasses
import json
import logging
import uuid
from contextlib import AsyncExitStack
from typing import Dict, List

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from asgiref.sync import sync_to_async
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelMessagesTypeAdapter,
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
    UserContent,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from chat.ai_sdk_types import (
    LanguageModelV1Source,
    SourceUIPart,
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


class UserIntent(BaseModel):
    """Model to represent the detected user intent."""

    web_search: bool = False


class AIAgentService:
    """Service class for AI-related operations (Pydantic-AI edition)."""

    def __init__(self, conversation):
        self.conversation = conversation

    # --------------------------------------------------------------------- #
    # Public streaming API (unchanged signatures)
    # --------------------------------------------------------------------- #

    def stream_text(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return only the assistant text deltas (legacy text mode)."""
        return convert_async_generator_to_sync(self.stream_text_async(messages, force_web_search))

    def stream_data(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return Vercel-AI-SDK formatted events."""
        return convert_async_generator_to_sync(self.stream_data_async(messages, force_web_search))

    # --------------------------------------------------------------------- #
    # Async internals
    # --------------------------------------------------------------------- #

    async def stream_text_async(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return only the assistant text deltas (legacy text mode)."""
        async for delta in self._run_agent(messages, force_web_search):
            if delta["type"] == "0":
                yield delta["payload"]

    async def stream_data_async(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return Vercel-AI-SDK formatted events."""
        async for delta in self._run_agent(messages, force_web_search):
            yield f"{delta['type']}:{json.dumps(delta['payload'])}\n"

    # --------------------------------------------------------------------- #
    # Core agent runner
    # --------------------------------------------------------------------- #

    async def _detect_user_intent(self, user_prompt: List[UserContent]) -> UserIntent:
        """
        Detect the user intent by calling a small LLM.

        Args:
            user_prompt (List[UserContent]): The user prompt to analyze.
        Returns:
            UserIntent: The detected user intent, indicating if a web search is needed.
        Raises:
            ImproperlyConfigured: If the AI configuration is not set.
        """
        if missing_settings := [
            setting
            for setting in (
                settings.AI_ROUTING_MODEL,
                settings.AI_ROUTING_MODEL_BASE_URL,
                settings.AI_ROUTING_MODEL_API_KEY,
                settings.AI_ROUTING_SYSTEM_PROMPT,
            )
            if not setting  # ie if setting is None or setting == ""
        ]:
            raise ImproperlyConfigured(
                f"AI routing model configuration not set: {missing_settings}"
            )

        agent = Agent(
            model=OpenAIModel(
                model_name=settings.AI_ROUTING_MODEL,
                provider=OpenAIProvider(
                    base_url=settings.AI_ROUTING_MODEL_BASE_URL,
                    api_key=settings.AI_ROUTING_MODEL_API_KEY,
                ),
            ),
            system_prompt=settings.AI_ROUTING_SYSTEM_PROMPT,
            output_type=NativeOutput([UserIntent]),
        )

        result = await agent.run(user_prompt)
        logger.debug("Detected user intent: %s", result)
        return result.output

    async def _run_agent(  # noqa: PLR0912, PLR0915
        self,
        messages: List[UIMessage],
        force_web_search: bool = False,
    ):  # pylint: disable=too-many-branches,too-many-statements, too-many-locals
        """Run the Pydantic AI agent and stream events."""
        if messages[-1].role != "user":
            return

        history = [ui_message_to_model_message(message) for message in messages[:-1]]
        prompt = ui_message_to_user_content(messages[-1])
        usage = {"promptTokens": 0, "completionTokens": 0}

        # Check is the user prompt requires web search
        if not settings.RAG_WEB_SEARCH_BACKEND:
            # If web search is not enabled, we can skip the intent detection
            user_intent = UserIntent(web_search=False)
            logger.info("Web search backend is disabled, skipping intent detection.")
        elif force_web_search:
            # While the only intent detection is web search, we can
            # skip the detection if the user has explicitly requested a web search.
            user_intent = UserIntent(web_search=True)
            logger.info("Web search requested by user, skipping intent detection.")
        else:
            user_intent: UserIntent = await self._detect_user_intent(prompt)
            logger.info("User intent detected: %s", user_intent.model_dump())

        logger.debug("User intent %s", user_intent)

        _user_initial_prompt_str = None
        _ui_sources = []
        if user_intent.web_search:  # might be forced by force_web_search
            search_backend = import_string(settings.RAG_WEB_SEARCH_BACKEND)
            search_results = search_backend().web_search(
                " ".join(prompt for prompt in prompt if isinstance(prompt, str))
            )

            if search_results.data:
                for idx, prompt_item in enumerate(prompt):
                    if isinstance(prompt_item, str):
                        _user_initial_prompt_str = str(prompt_item)
                        prompt[idx] = settings.RAG_WEB_SEARCH_PROMPT_UPDATE.format(
                            search_results=search_results.to_prompt(),
                            user_prompt=prompt_item,
                        )
                        break

                _unique_sources = set()
                for result in search_results.data:
                    logger.debug("Search result: %s", result.model_dump())

                    # Several chunks may come from the same URL,
                    # so we need to ensure we don't duplicate sources.
                    if result.url in _unique_sources:
                        logger.debug("Skipping duplicated source: %s", result.url)
                        continue

                    _unique_sources.add(result.url)
                    url_source = LanguageModelV1Source(
                        source_type="url",
                        id=str(uuid.uuid4()),
                        url=result.url,
                        providerMetadata={},
                    )
                    _ui_sources.append(SourceUIPart(type="source", source=url_source))

                    yield {
                        "type": "h",
                        "payload": url_source.model_dump(mode="json"),
                    }
            elif force_web_search:
                logger.warning("Web search was forced but no results were found.")
                yield {
                    "type": "h",
                    "payload": {
                        "source_type": "error",
                        "id": str(uuid.uuid4()),
                        "error": "No web search results found.",
                    },
                }
                return
            else:
                logger.warning("No web search results found, continuing without web search.")

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
            final_output=run.result.new_messages(),
            raw_final_output=run.result.new_messages_json(),
            usage=usage,
            user_initial_prompt_str=_user_initial_prompt_str,
            ui_sources=_ui_sources,
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
        *,
        final_output: List[ModelRequest | ModelMessage],
        raw_final_output: bytes,
        usage: Dict[str, int],
        user_initial_prompt_str: str | None,
        ui_sources: List[SourceUIPart] = None,
    ):  # pylint: disable=too-many-arguments
        """
        Save everything related to the conversation.

        There are two things to improve here:
         - The way we "fix" the user prompt when web search is used. This implementation is
           a bit hacky and suboptimal.
         - The way we need to add the UI sources to the final output message.

        Args:
            final_output (List[ModelRequest | ModelMessage]): The final output from the agent.
            raw_final_output (bytes): The raw final output in bytes.
            usage (Dict[str, int]): The token usage statistics.
            user_initial_prompt_str (str | None): The initial user prompt string, if any.
            ui_sources (List[SourceUIPart]): Optional UI sources to include in the conversation.
        """
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

        # Remove the RAG web search prompt if it was added
        if user_initial_prompt_str:  # pylint: disable=too-many-nested-blocks
            for part in _merged_final_output_request.parts:
                logger.debug("Part type: %s, content: %s", type(part), part.content)
                if isinstance(part, UserPromptPart):
                    if isinstance(part.content, str) and part.content.startswith(
                        settings.RAG_WEB_SEARCH_PROMPT_UPDATE[:30]
                    ):
                        logger.debug("Part content: %s", part.content)
                        part.content = user_initial_prompt_str
                    elif isinstance(part.content, list):
                        for idx, content_part in enumerate(part.content):
                            if isinstance(content_part, str) and content_part.startswith(
                                settings.RAG_WEB_SEARCH_PROMPT_UPDATE[:30]
                            ):
                                logger.debug("Part content: %s", content_part)
                                part.content[idx] = user_initial_prompt_str

        _output_ui_message = model_message_to_ui_message(_merged_final_output_message)
        if ui_sources:
            _output_ui_message.parts += ui_sources

        self.conversation.messages += [
            model_message_to_ui_message(_merged_final_output_request),
            _output_ui_message,
        ]
        self.conversation.agent_usage = usage

        logger.debug(
            "raw_final_output: %s %s",
            raw_final_output.decode("utf-8"),
            json.loads(raw_final_output.decode("utf-8")),
        )
        self.conversation.openai_messages += json.loads(raw_final_output.decode("utf-8"))

        self.conversation.save()
