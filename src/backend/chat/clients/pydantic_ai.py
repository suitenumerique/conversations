"""
Pydantic-AI based AIAgentService.

This file replaces the previous OpenAI-specific client with a Pydantic-AI
implementation while keeping the *exact* same public API so that no
changes are needed in views.py or tests.
"""

import dataclasses
import json
import logging
import time
import uuid
from contextlib import AsyncExitStack, ExitStack
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from asgiref.sync import sync_to_async
from langfuse import get_client
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.messages import (
    BinaryContent,
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
    ToolReturn,
    ToolReturnPart,
)
from pydantic_ai.result import FinalResult

from core.feature_flags.helpers import is_feature_enabled

from chat import models
from chat.agents.conversation import ConversationAgent
from chat.agents.summarize import hand_off_to_summarization_agent
from chat.ai_sdk_types import (
    LanguageModelV1Source,
    SourceUIPart,
    UIMessage,
)
from chat.clients.async_to_sync import convert_async_generator_to_sync
from chat.clients.exceptions import StreamCancelException
from chat.clients.pydantic_ui_message_converter import (
    model_message_to_ui_message,
    ui_message_to_user_content,
)
from chat.mcp_servers import get_mcp_servers
from chat.tools.document_search_rag import add_document_rag_search_tool
from chat.vercel_ai_sdk.core import events_v4, events_v5
from chat.vercel_ai_sdk.encoder import EventEncoder

logger = logging.getLogger(__name__)

User = get_user_model()


@dataclasses.dataclass
class ContextDeps:
    """Dependencies for context management."""

    conversation: models.ChatConversation
    user: User
    web_search_enabled: bool = False


def get_model_configuration(model_hrid: str):
    """Get the model configuration from settings."""
    try:
        return settings.LLM_CONFIGURATIONS[model_hrid]
    except KeyError as exc:
        raise ImproperlyConfigured(f"LLM model configuration '{model_hrid}' not found.") from exc


class AIAgentService:  # pylint: disable=too-many-instance-attributes
    """Service class for AI-related operations (Pydantic-AI edition)."""

    def __init__(self, conversation: models.ChatConversation, user, model_hrid=None, language=None):
        """
        Initialize the AI agent service.

        Args:
            conversation: The chat conversation instance
            user: The authenticated user instance, only used for dynamic feature flags
        """
        self.conversation = conversation
        self.user = user  # authenticated user only
        self.model_hrid = model_hrid or settings.LLM_DEFAULT_MODEL_HRID  # HRID of the model to use
        self.language = language  # might be None
        self._last_stop_check = 0

        self._store_analytics = settings.LANGFUSE_ENABLED and user.allow_conversation_analytics
        self.event_encoder = EventEncoder("v4")  # Always use v4 for now

        self._support_streaming = True
        if (streaming := get_model_configuration(self.model_hrid).supports_streaming) is not None:
            self._support_streaming = streaming

        # Feature flags
        self._is_document_upload_enabled = is_feature_enabled(self.user, "document_upload")
        self._is_web_search_enabled = is_feature_enabled(self.user, "web_search")
        self._fake_streaming_delay = settings.FAKE_STREAMING_DELAY

        self._context_deps = ContextDeps(
            conversation=conversation,
            user=user,
            web_search_enabled=self._is_web_search_enabled,
        )

        self.conversation_agent = ConversationAgent(
            model_hrid=self.model_hrid,
            language=self.language,
            instrument=self._store_analytics,
            deps_type=ContextDeps,
        )

    @property
    def _stop_cache_key(self):
        return f"streaming:stop:{self.conversation.pk}"

    # --------------------------------------------------------------------- #
    # Public streaming API (unchanged signatures)
    # --------------------------------------------------------------------- #

    def stream_text(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return only the assistant text deltas (legacy text mode)."""
        return convert_async_generator_to_sync(self.stream_text_async(messages, force_web_search))

    def stream_data(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return Vercel-AI-SDK formatted events."""
        return convert_async_generator_to_sync(self.stream_data_async(messages, force_web_search))

    def stop_streaming(self):
        """
        Stop the current streaming operation.

        This method is a placeholder for stopping the streaming operation.
        """
        logger.info("Stopping streaming for conversation %s", self.conversation.id)
        cache.set(self._stop_cache_key, "1", timeout=30 * 60)  # 30 minutes timeout

    # --------------------------------------------------------------------- #
    # Async internals
    # --------------------------------------------------------------------- #

    async def stream_text_async(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return only the assistant text deltas (legacy text mode)."""
        await self._clean()
        with ExitStack() as stack:
            if self._store_analytics:
                span = stack.enter_context(get_client().start_as_current_span(name="conversation"))
                span.update_trace(user_id=str(self.user.sub), session_id=str(self.conversation.pk))

            async for event in self._run_agent(messages, force_web_search):
                if stream_text := self.event_encoder.encode_text(event):
                    yield stream_text

    async def stream_data_async(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return Vercel-AI-SDK formatted events."""
        await self._clean()
        with ExitStack() as stack:
            if self._store_analytics:
                span = stack.enter_context(get_client().start_as_current_span(name="conversation"))
                span.update_trace(user_id=str(self.user.sub), session_id=str(self.conversation.pk))
            async for event in self._run_agent(messages, force_web_search):
                if stream_data := self.event_encoder.encode(event):
                    yield stream_data

    async def _agent_stop_streaming(self, force_cache_check: Optional[bool] = False) -> None:
        """Check if the agent should stop streaming."""
        now = time.time()  # Current time in seconds since epoch

        # Check if we should skip the cache check to avoid frequent checks
        # This is useful to avoid unnecessary cache checks during streaming
        # Check every 2 seconds
        if not force_cache_check and now - self._last_stop_check < 2:
            return
        self._last_stop_check = now

        if await cache.aget(self._stop_cache_key):
            logger.info("Streaming stopped by cache key for conversation %s", self.conversation.id)
            await cache.adelete(self._stop_cache_key)
            raise StreamCancelException()
        return

    async def _clean(self):
        """
        Clean up the agent service.

        This method is called when the agent service is no longer needed.
        It can be used to release resources or perform any necessary cleanup.
        """
        self._last_stop_check = 0
        await cache.adelete(self._stop_cache_key)

    # --------------------------------------------------------------------- #
    # Core agent runner
    # --------------------------------------------------------------------- #
    async def parse_input_documents(self, documents: List[BinaryContent]):
        """
        Parse and store input documents in the conversation's document store.
        """
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        document_store = document_store_backend(self.conversation.collection_id)
        if not document_store.collection_id:
            # Create a new collection for the conversation
            collection_id = document_store.create_collection(
                name=f"conversation-{self.conversation.pk}",
            )
            self.conversation.collection_id = str(collection_id)
            await self.conversation.asave(update_fields=["collection_id", "updated_at"])

        for document in documents:
            parsed_content = document_store.parse_and_store_document(
                name=document.identifier,
                content_type=document.media_type,
                content=document.data,
            )
            await models.ChatConversationContext.objects.acreate(
                conversation=self.conversation,
                kind=models.ChatConversationContextKind.DOCUMENT.value,
                name=document.identifier,
                content=parsed_content,
            )

    def prepare_prompt(
        self, message: UIMessage
    ) -> Tuple[str, List[BinaryContent], List[BinaryContent]]:
        """
        Prepare the user prompt for the agent.

        This method is used to convert a UIMessage into a format suitable for the agent.
        It extracts the user content from the message and returns it as a list of UserContent.
        """
        user_content = ui_message_to_user_content(message)

        user_prompt = []
        attachment_images = []
        attachment_documents = []
        attachment_audio = []
        attachment_video = []
        for content in user_content:
            if isinstance(content, str):
                user_prompt.append(content)
            elif isinstance(content, BinaryContent):
                if content.is_audio:
                    attachment_audio.append(content)
                elif content.is_video:
                    attachment_video.append(content)
                elif content.is_image:
                    attachment_images.append(content)
                else:
                    attachment_documents.append(content)
            else:
                # Should never happen, but just in case
                raise ValueError(f"Unsupported UserContent type: {type(content)}")

        if any(attachment_audio):
            # Should be handled by the frontend, but just in case
            raise ValueError("Audio attachments are not supported in the current implementation.")
        if any(attachment_video):
            # Should be handled by the frontend, but just in case
            raise ValueError("Video attachments are not supported in the current implementation.")

        if len(user_prompt) != 1:
            raise ValueError(
                "User prompt must contain exactly one text part, "
                f"but got {len(user_prompt)} parts: {user_prompt}"
            )

        return user_prompt[0], attachment_images, attachment_documents

    async def _run_agent(  # noqa: PLR0912, PLR0915 # pylint: disable=too-many-branches,too-many-statements, too-many-locals, too-many-return-statements
        self,
        messages: List[UIMessage],
        force_web_search: bool = False,
    ) -> events_v4.Event | events_v5.Event:
        """Run the Pydantic AI agent and stream events."""
        if messages[-1].role != "user":
            return

        # Langfuse settings
        if self._store_analytics:
            langfuse = get_client()
            langfuse.update_current_trace(
                session_id=str(self.conversation.pk),
                user_id=str(self.user.sub),
            )

        history = ModelMessagesTypeAdapter.validate_python(self.conversation.pydantic_messages)
        user_prompt, input_images, input_documents = self.prepare_prompt(messages[-1])

        if self._store_analytics:
            langfuse.update_current_trace(input=user_prompt)

        usage = {"promptTokens": 0, "completionTokens": 0}

        conversation_has_documents = self._is_document_upload_enabled and (
            bool(self.conversation.collection_id)
            or bool(
                await models.ChatConversationContext.objects.filter(
                    conversation=self.conversation,
                    kind=models.ChatConversationContextKind.DOCUMENT.value,
                ).aexists()
            )
        )

        if not self._is_document_upload_enabled and input_documents:
            logger.warning("Document upload feature is disabled, ignoring input documents.")
            input_documents = []

        if input_documents:
            _tool_call_id = str(uuid.uuid4())
            yield events_v4.ToolCallPart(
                tool_call_id=_tool_call_id,
                tool_name="document_parsing",
                args={
                    "documents": [
                        {
                            "identifier": doc.identifier,
                        }
                        for doc in input_documents
                    ],
                },
            )
            try:
                await self.parse_input_documents(input_documents)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error parsing input documents: %s", exc)
                yield events_v4.ToolResultPart(
                    tool_call_id=_tool_call_id,
                    result={"state": "error", "error": str(exc)},
                )
                yield events_v4.FinishMessagePart(
                    finish_reason=events_v4.FinishReason.ERROR,
                    usage=events_v4.Usage(
                        prompt_tokens=usage["promptTokens"],
                        completion_tokens=usage["completionTokens"],
                    ),
                )
                return
            if not conversation_has_documents:
                conversation_has_documents = True

            yield events_v4.ToolResultPart(
                tool_call_id=_tool_call_id,
                result={"state": "done"},
            )

        await self._agent_stop_streaming(force_cache_check=True)

        if force_web_search and not self._is_web_search_enabled:
            logger.warning("Web search is forced but the feature is disabled, ignoring.")
            force_web_search = False

        web_search_tool_name = self.conversation_agent.get_web_search_tool_name()
        if force_web_search and not web_search_tool_name:
            logger.warning("Web search is forced but no web search tool is available, ignoring.")
            force_web_search = False

        if force_web_search:

            @self.conversation_agent.system_prompt
            def force_web_search_prompt() -> str:
                """Dynamic system prompt function to force web search."""
                return (
                    f"You must call the {web_search_tool_name} tool "
                    "before answering the user request."
                )

        _tool_is_streaming = False
        _model_response_message_id = None
        async with AsyncExitStack() as stack:
            # MCP servers (if any) can be initialized here
            mcp_servers = [await stack.enter_async_context(mcp) for mcp in get_mcp_servers()]

            if conversation_has_documents:
                add_document_rag_search_tool(self.conversation_agent)

                @self.conversation_agent.system_prompt
                def summarize_instructions() -> str:
                    """Dynamic system prompt function to add RAG instructions if any."""
                    return (
                        "If the user wants a summary of document(s), invoke summarize tool "
                        "without asking the user for the document itself. The tool will handle "
                        "any necessary extraction and summarization based on the internal context."
                    )

            _final_output_from_tool = None
            _ui_sources = []

            # Help Mistral to prevent `Unexpected role 'user' after role 'tool'` error.
            if history and history[-1].kind == "request":
                if history[-1].parts[-1].part_kind == "tool-return":
                    history.append(ModelResponse(parts=[TextPart(content="ok")], kind="response"))

            async with self.conversation_agent.iter(
                [user_prompt] + input_images,
                message_history=history,
                deps=self._context_deps,
                toolsets=mcp_servers,
                output_type=(
                    [ToolOutput(hand_off_to_summarization_agent, name="summarize"), str]
                    if conversation_has_documents
                    else str
                ),
            ) as run:
                async for node in run:
                    await self._agent_stop_streaming()
                    if Agent.is_user_prompt_node(node):
                        # A user prompt node => The user has provided input
                        pass

                    elif Agent.is_model_request_node(node):  # pylint: disable=too-many-nested-blocks
                        # A model request node => agent is asking the model to generate a response
                        if not self._support_streaming:
                            result = await node.run(run.ctx)
                            logger.debug("node.run result: %s", result)
                            for part in result.model_response.parts:
                                if isinstance(part, TextPart):
                                    if self._fake_streaming_delay:
                                        for i in range(0, len(part.content), 4):
                                            await self._agent_stop_streaming()
                                            yield events_v4.TextPart(text=part.content[i : i + 4])
                                            time.sleep(self._fake_streaming_delay)
                                    else:
                                        yield events_v4.TextPart(text=part.content)
                                elif isinstance(part, ToolCallPart):
                                    yield events_v4.ToolCallPart(
                                        tool_call_id=part.tool_call_id,
                                        tool_name=part.tool_name,
                                        args=json.loads(part.args) if part.args else {},
                                    )
                                elif isinstance(part, ThinkingPart):
                                    yield events_v4.ReasoningPart(reasoning=part.content)
                                else:
                                    logger.warning(
                                        "Unknown part type in model response: %s %s",
                                        type(part),
                                        dataclasses.asdict(part),
                                    )
                            continue

                        async with node.stream(run.ctx) as request_stream:
                            async for event in request_stream:
                                await self._agent_stop_streaming()
                                logger.debug("Received request_stream event: %s", type(event))
                                if isinstance(event, PartStartEvent):
                                    logger.debug("PartStartEvent: %s", dataclasses.asdict(event))

                                    if isinstance(event.part, TextPart):
                                        yield events_v4.TextPart(text=event.part.content)
                                    elif isinstance(event.part, ToolCallPart):
                                        yield events_v4.ToolCallStreamingStartPart(
                                            tool_call_id=event.part.tool_call_id,
                                            tool_name=event.part.tool_name,
                                        )
                                    elif isinstance(event.part, ThinkingPart):
                                        yield events_v4.ReasoningPart(
                                            reasoning=event.part.content,
                                        )

                                elif isinstance(event, PartDeltaEvent):
                                    logger.debug(
                                        "PartDeltaEvent: %s %s",
                                        type(event),
                                        dataclasses.asdict(event),
                                    )
                                    if isinstance(event.delta, TextPartDelta):
                                        yield events_v4.TextPart(text=event.delta.content_delta)
                                    elif isinstance(event.delta, ToolCallPartDelta):
                                        _tool_is_streaming = True
                                        yield events_v4.ToolCallDeltaPart(
                                            tool_call_id=event.delta.tool_call_id,
                                            args_text_delta=event.delta.args_delta,
                                        )
                                    elif isinstance(event.delta, ThinkingPartDelta):
                                        yield events_v4.ReasoningPart(
                                            reasoning=event.delta.content_delta,
                                        )

                    elif Agent.is_call_tools_node(node):
                        # A handle-response node => The model returned some data,
                        # potentially calls a tool
                        async with node.stream(run.ctx) as handle_stream:
                            async for event in handle_stream:
                                await self._agent_stop_streaming()
                                logger.debug(
                                    "Received request_stream event: %s, %s",
                                    type(event),
                                    dataclasses.asdict(event),
                                )
                                if isinstance(event, FunctionToolCallEvent):
                                    if not _tool_is_streaming:
                                        yield events_v4.ToolCallPart(
                                            tool_call_id=event.tool_call_id,
                                            tool_name=event.part.tool_name,
                                            args=json.loads(event.part.args)
                                            if event.part.args
                                            else {},
                                        )
                                elif isinstance(event, FunctionToolResultEvent):
                                    if isinstance(event.result, ToolReturnPart):
                                        if event.result.metadata and (
                                            sources := event.result.metadata.get("sources")
                                        ):
                                            for source_url in sources:
                                                url_source = LanguageModelV1Source(
                                                    sourceType="url",
                                                    id=str(uuid.uuid4()),
                                                    url=source_url,
                                                    providerMetadata={},
                                                )
                                                _new_source_ui = SourceUIPart(
                                                    type="source", source=url_source
                                                )
                                                _ui_sources.append(_new_source_ui)
                                                yield events_v4.SourcePart(
                                                    **_new_source_ui.source.model_dump()
                                                )

                                        yield events_v4.ToolResultPart(
                                            tool_call_id=event.tool_call_id,
                                            result=event.result.content,
                                        )
                                    elif isinstance(event.result, RetryPromptPart):
                                        yield events_v4.ToolResultPart(
                                            tool_call_id=event.tool_call_id,
                                            result=event.result.content,
                                        )
                                    else:
                                        logger.warning(
                                            "Unexpected tool result type: %s %s",
                                            type(event.result),
                                            dataclasses.asdict(event.result),
                                        )
                    elif Agent.is_end_node(node):
                        # Once an End node is reached, the agent run is complete
                        logger.debug("v: %s", dataclasses.asdict(node))

                        # Enforce the message ID to store the trace ID and allow scoring later
                        # We use the start step part (to set the message ID) even if it's
                        # not the purpose of this event, but Vercel AI SDK does not
                        # have a better place to set the message ID and we only want to enforce
                        # The last message to store the trace ID...
                        if _model_response_message_id:
                            logger.error("_model_response_message_id already set")
                        _model_response_message_id = (
                            str(uuid.uuid4())
                            if not self._store_analytics
                            else f"trace-{langfuse.get_current_trace_id()}"
                        )
                        yield events_v4.StartStepPart(
                            message_id=_model_response_message_id,
                        )

                        if (
                            isinstance(node.data, FinalResult)
                            and node.data.tool_name == "summarize"
                        ):
                            yield events_v4.ToolResultPart(
                                tool_call_id=node.data.tool_call_id,
                                result={"state": "done"},  # content not needed here
                            )
                            final_output = node.data.output
                            if isinstance(final_output, ToolReturn):
                                _final_output_from_tool = final_output.content
                                yield events_v4.TextPart(text=final_output.content)

                                if final_output.metadata and (
                                    sources := final_output.metadata.get("sources")
                                ):
                                    for source_url in sources:
                                        url_source = LanguageModelV1Source(
                                            sourceType="url",
                                            id=str(uuid.uuid4()),
                                            url=source_url,
                                            providerMetadata={},
                                        )
                                        _new_source_ui = SourceUIPart(
                                            type="source", source=url_source
                                        )
                                        _ui_sources.append(_new_source_ui)
                                        yield events_v4.SourcePart(
                                            **_new_source_ui.source.model_dump()
                                        )
                            else:
                                logger.warning(
                                    "Unexpected final result type: %s %s",
                                    type(final_output),
                                    final_output,
                                )

                    else:
                        logger.warning(
                            "Unknown node type encountered: %s",
                            type(node),
                        )

                # Final usage summary
                final_usage = run.usage()
                usage["promptTokens"] = final_usage.input_tokens
                usage["completionTokens"] = final_usage.output_tokens

        await self._agent_stop_streaming(force_cache_check=True)

        # Persist conversation
        await sync_to_async(self._update_conversation)(
            final_output=run.result.new_messages(),
            raw_final_output=run.result.new_messages_json(),
            usage=usage,
            final_output_from_tool=_final_output_from_tool,
            ui_sources=_ui_sources,
            model_response_message_id=_model_response_message_id,
        )

        if self._store_analytics:
            langfuse.update_current_trace(output=run.result.output)

        # Vercel finish message
        yield events_v4.FinishMessagePart(
            finish_reason=events_v4.FinishReason.STOP,
            usage=events_v4.Usage(
                prompt_tokens=usage["promptTokens"],
                completion_tokens=usage["completionTokens"],
            ),
        )

    def _update_conversation(  # noqa: PLR0913
        self,
        *,
        final_output: List[ModelRequest | ModelMessage],
        raw_final_output: bytes,
        usage: Dict[str, int],
        final_output_from_tool: str | None,
        ui_sources: List[SourceUIPart] = None,
        model_response_message_id: str | None = None,
    ):  # pylint: disable=too-many-arguments
        """
        Save everything related to the conversation.

        Things to improve here:
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
            ]
            + ([TextPart(content=final_output_from_tool)] if final_output_from_tool else []),
            kind="response",
        )

        _output_ui_message = model_message_to_ui_message(_merged_final_output_message)
        if ui_sources:
            _output_ui_message.parts += ui_sources
        if model_response_message_id:
            _output_ui_message.id = model_response_message_id
        else:
            logger.warning("model_response_message_id is None")

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
        self.conversation.pydantic_messages += json.loads(raw_final_output.decode("utf-8"))

        self.conversation.save()
