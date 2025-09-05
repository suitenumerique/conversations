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
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils import formats, timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from asgiref.sync import sync_to_async
from langfuse import get_client
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
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
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from core.enums import get_language_name
from core.feature_flags.helpers import is_feature_enabled

from chat.agent_rag.document_search.albert_api import AlbertRagDocumentSearch
from chat.ai_sdk_types import (
    LanguageModelV1Source,
    SourceUIPart,
    UIMessage,
)
from chat.clients.async_to_sync import convert_async_generator_to_sync
from chat.clients.exceptions import StreamCancelException, WebSearchEmptyException
from chat.clients.pydantic_ui_message_converter import (
    model_message_to_ui_message,
    ui_message_to_user_content,
)
from chat.mcp_servers import get_mcp_servers
from chat.tools import get_pydantic_tools_by_name
from chat.vercel_ai_sdk.core import events_v4, events_v5
from chat.vercel_ai_sdk.encoder import EventEncoder

logger = logging.getLogger(__name__)


def _get_pydantic_agent(model_hrid, mcp_servers=None, **kwargs) -> Agent:
    """Get the PydanticAI Agent instance with the configured settings."""
    try:
        _model = settings.LLM_CONFIGURATIONS[model_hrid]
    except KeyError as exc:
        raise ImproperlyConfigured(f"LLM model configuration '{model_hrid}' not found.") from exc

    _model_instance = OpenAIModel(
        model_name=_model.model_name,
        provider=OpenAIProvider(
            base_url=_model.provider.base_url,
            api_key=_model.provider.api_key,
        )
        if _model.provider
        else None,
    )
    _system_prompt = _model.system_prompt
    _tools = [get_pydantic_tools_by_name(tool_name) for tool_name in _model.tools]

    return Agent(
        model=_model_instance,
        system_prompt=_system_prompt,
        mcp_servers=mcp_servers or [],
        tools=_tools,
        **kwargs,
    )


def _build_pydantic_agent(
    mcp_servers, model_hrid=None, language=None, instrument=False
) -> Agent[None, str]:
    """Create a Pydantic AI Agent instance with the configured settings."""
    model_hrid = model_hrid or settings.LLM_DEFAULT_MODEL_HRID

    agent = _get_pydantic_agent(model_hrid, mcp_servers, instrument=instrument)

    @agent.system_prompt
    def add_the_date() -> str:
        """
        Dynamic system prompt function to add the current date.

        Warning: this will always use the date in the server timezone,
        not the user's timezone...
        """
        _formatted_date = formats.date_format(timezone.now(), "l d/m/Y", use_l10n=False)
        return f"Today is {_formatted_date}."

    @agent.system_prompt
    def enforce_response_language() -> str:
        """Dynamic system prompt function to set the expected language to use."""
        return f"Answer in {get_language_name(language).lower()}." if language else ""

    return agent


def _build_routing_agent(model_hrid=None, instrument=False) -> Agent[None, str] | None:
    """
    Create a Pydantic AI routing Agent instance with the configured settings.

    This agent is used to detect the user intent from the user prompt.

    Args:
        model_hrid (str | None): The HRID of the routing model to use.
            If None, the default routing model from settings will be used.
    Returns:
        Agent | None: The Pydantic AI Agent instance or None if not configured.
    Raises:
        ImproperlyConfigured: If the routing model configuration is invalid.
    """
    model_hrid = model_hrid or settings.LLM_ROUTING_MODEL_HRID

    try:
        agent = _get_pydantic_agent(
            model_hrid,
            output_type=NativeOutput([UserIntent]),
            instrument=instrument,
        )
    except ImproperlyConfigured:
        logger.info("AI routing model does not exist -> disabled")
        return None

    # Simple detection of configuration not set
    if not agent.model.model_name:
        logger.info("AI routing model configuration not set -> disabled")
        return None

    return agent


class UserIntent(BaseModel):
    """Model to represent the detected user intent."""

    web_search: bool = False
    attachment_summary: bool = False


class AIAgentService:  # pylint: disable=too-many-instance-attributes
    """Service class for AI-related operations (Pydantic-AI edition)."""

    def __init__(self, conversation, user, model_hrid=None, language=None):
        """
        Initialize the AI agent service.

        Args:
            conversation: The chat conversation instance
            user: The authenticated user instance, only used for dynamic feature flags
        """
        self.conversation = conversation
        self.user = user  # authenticated user only
        self.model_hrid = model_hrid  # HRID of the model to use, might be None
        self.language = language  # might be None
        self._last_stop_check = 0

        self._store_analytics = settings.LANGFUSE_ENABLED and user.allow_conversation_analytics
        self.event_encoder = EventEncoder("v4")  # Always use v4 for now

        # Feature flags
        self._is_document_upload_enabled = is_feature_enabled(self.user, "document_upload")
        self._is_web_search_enabled = is_feature_enabled(self.user, "web_search")

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

    async def _detect_user_intent(self, user_prompt: str) -> UserIntent:
        """
        Detect the user intent by calling a small LLM.

        Args:
            user_prompt str: The user prompt to analyze.
        Returns:
            UserIntent: The detected user intent, indicating if a web search is needed.
        Raises:
            ImproperlyConfigured: If the AI configuration is not set.
        """
        if not any([self._is_web_search_enabled, self._is_document_upload_enabled]):
            logger.info(
                "No web search or document upload features enabled, skipping intent detection.",
            )
            return UserIntent()

        agent = _build_routing_agent(instrument=self._store_analytics)
        if not agent:
            return UserIntent()

        result = await agent.run(user_prompt)
        logger.debug("Detected user intent: %s", result)

        # Disable some intent if the project settings do not allow it
        if not settings.RAG_WEB_SEARCH_BACKEND:
            # If web search is not enabled, we can skip the intent detection
            result.output.web_search = False
            logger.info("Web search backend is disabled, skipping intent detection.")

        if not self._is_document_upload_enabled:
            # If document upload is not enabled, we can skip the attachment summary intent
            result.output.attachment_summary = False
            logger.info("Document upload feature is disabled, skipping attachment summary intent.")

        if not self._is_web_search_enabled:
            # If web search is not enabled, we can skip the web search intent
            result.output.web_search = False
            logger.info("Web search feature is disabled, skipping web search intent.")

        return result.output

    def parse_input_documents(self, documents: List[BinaryContent]):
        """
        Parse and store input documents in the conversation's document store.
        """
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
        document_store = document_store_backend(self.conversation)
        for document in documents:
            document_store.parse_and_store_document(
                name=document.identifier,
                content_type=document.media_type,
                content=document.data,
            )

    def perform_rag(
        self,
        user_prompt: str,
        intent_web_search: bool = False,
        force_web_search: bool = False,
        document_search: bool = False,
    ) -> Tuple[str, List[SourceUIPart]]:
        """
        Perform RAG (Retrieval-Augmented Generation) based on the conversation settings.

        Args:
            web_search (bool): Whether to perform a web search.
            document_search (bool): Whether to query attachments.
        """
        ui_sources = []

        if intent_web_search or force_web_search:
            web_search_backend = import_string(settings.RAG_WEB_SEARCH_BACKEND)
            web_search_results = web_search_backend().web_search(user_prompt)
        else:
            web_search_results = None

        if force_web_search and web_search_results is None:
            logger.error("Forced web search was requested but no results were found.")
            raise WebSearchEmptyException()

        if document_search:
            document_search_backend = AlbertRagDocumentSearch(self.conversation)
            document_search_results = document_search_backend.search(user_prompt)
        else:
            document_search_results = None

        if web_search_results is None and document_search_results is None:
            logger.warning("No web search or document search results found, skipping RAG.")
            return "", ui_sources

        prompted_results = "\n\n".join(
            search_results.to_prompt()
            for search_results in [web_search_results, document_search_results]
            if search_results is not None
        )
        new_prompt = settings.RAG_WEB_SEARCH_PROMPT_UPDATE.format(
            search_results=prompted_results, user_prompt=user_prompt
        )

        _unique_sources = set()
        for search_results in [web_search_results, document_search_results]:
            if search_results is None:
                continue

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
                ui_sources.append(SourceUIPart(type="source", source=url_source))

        return new_prompt, ui_sources

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

        # Feature flag management
        if force_web_search and not self._is_web_search_enabled:
            logger.warning("Web search feature is disabled, ignoring force_web_search.")
            force_web_search = False

        if any([input_images, input_documents]) and not self._is_document_upload_enabled:
            logger.warning("Document upload feature is disabled, ignoring input documents.")
            input_images = []
            input_documents = []

        # Detect the user intent
        if not force_web_search:
            user_intent: UserIntent = await self._detect_user_intent(user_prompt)
            logger.info("User intent detected: %s", user_intent.model_dump())
        else:
            # If the user has requested a web search, we consider it as the no intent
            # of document summarization.
            user_intent = UserIntent()

        if input_documents and user_intent.attachment_summary:
            # If the user has provided documents and requested a summary,
            # we need to handle that.
            logger.warning(
                "Attachment summarization is not supported yet, ignoring the user intent."
            )
            user_intent.attachment_summary = False
            yield events_v4.ErrorPart(error="attachment_summary_not_supported")
            return

        await self._agent_stop_streaming(force_cache_check=True)

        # If user uploaded documents and did not enforce a web search, we disable the intent
        if input_documents and not force_web_search:
            user_intent.web_search = False
            logger.info("User intent web search disabled due to input documents.")

        conversation_has_documents = bool(self.conversation.collection_id)
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
            self.parse_input_documents(input_documents)
            if not conversation_has_documents:
                conversation_has_documents = True
                await self.conversation.asave(update_fields=["collection_id", "updated_at"])

            yield events_v4.ToolResultPart(
                tool_call_id=_tool_call_id,
                result={"state": "done"},
            )

        await self._agent_stop_streaming(force_cache_check=True)

        # Prepare the prompt for the agent
        try:
            _new_prompt, _ui_sources = self.perform_rag(
                user_prompt=user_prompt,
                intent_web_search=user_intent.web_search,
                force_web_search=force_web_search,
                document_search=conversation_has_documents,
            )
        except WebSearchEmptyException:
            yield events_v4.SourcePart(
                id=str(uuid.uuid4()),
                url=str(_("No web search results found.")),
            )
            return

        _user_initial_prompt_str = None
        if _new_prompt:
            _user_initial_prompt_str = str(user_prompt)  # copy the original user prompt
            user_prompt = _new_prompt
            for _ui_source in _ui_sources:
                yield events_v4.SourcePart(**_ui_source.source.model_dump())

        async with AsyncExitStack() as stack:
            # MCP servers (if any) can be initialized here
            mcp_servers = [await stack.enter_async_context(mcp) for mcp in get_mcp_servers()]

            async with _build_pydantic_agent(
                mcp_servers,
                model_hrid=self.model_hrid,
                language=self.language,
                instrument=self._store_analytics,
            ).iter(
                [user_prompt] + input_images,
                message_history=history,
            ) as run:
                async for node in run:
                    await self._agent_stop_streaming()
                    if Agent.is_user_prompt_node(node):
                        # A user prompt node => The user has provided input
                        pass

                    elif Agent.is_model_request_node(node):
                        # A model request node => We can stream tokens from the model's request
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

        await self._agent_stop_streaming(force_cache_check=True)

        # Persist conversation
        await sync_to_async(self._update_conversation)(
            final_output=run.result.new_messages(),
            raw_final_output=run.result.new_messages_json(),
            usage=usage,
            user_initial_prompt_str=_user_initial_prompt_str,
            ui_sources=_ui_sources,
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
        self.conversation.pydantic_messages += json.loads(raw_final_output.decode("utf-8"))

        self.conversation.save()
