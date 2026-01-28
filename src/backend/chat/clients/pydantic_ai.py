# pylint: disable=too-many-lines
"""
Pydantic-AI based AIAgentService.

This file replaces the previous OpenAI-specific client with a Pydantic-AI
implementation while keeping the *exact* same public API so that no
changes are needed in views.py or tests.

## High-Level Flow

1. **Initialization**: `AIAgentService` is created with a conversation and user.
   Feature flags, model config, and the conversation agent are set up.

2. **Streaming Entry Points**: `stream_text()` or `stream_data()` are called
   with user messages. These wrap async generators for sync consumption.

3. **Agent Execution** (`_run_agent`):
   a. Validate last message is from user
   b. Setup Langfuse tracing (if enabled)
   c. Prepare agent run (load history, process URLs, extract prompt/attachments)
   d. Handle input documents (parse, store in RAG, emit progress events)
   e. Configure tools (web search, RAG search, summarization)
   f. Run the Pydantic-AI agent iteration loop
   g. Process each node type (user prompt, model request, tool calls, end)
   h. Finalize (save conversation, generate title, emit finish events)

## Document Handling Flow

Documents attached to messages go through several stages:

1. **Upload** : Files are uploaded to object storage with keys
   like `{conversation_pk}/attachments/{filename}`. URLs use `/media-key/` prefix.

2. **Extraction** (`_prepare_prompt`): Documents are extracted from the UIMessage
   and separated from images. Audio/video attachments are rejected.

3. **Parsing** (`_handle_input_documents` → `_parse_input_documents`):
   - Validates document URLs belong to the conversation (security check)
   - Creates a vector store collection if none exists
   - For each document:
     - Retrieves content from object storage
     - Parses and stores in the vector store (chunked, embedded)
     - Creates a markdown attachment for non-text files
   - Emits tool call events so the UI shows parsing progress

4. **RAG Search** (`_setup_rag_tools`): When documents exist, the agent gets:
   - `document_rag_search` tool: Semantic search over document chunks
   - `summarize` tool: Full document summarization
   - Instructions informing the model that documents are available

## Streaming Architecture

Events flow through several layers:

    _run_agent (yields events)
        ↓
    _stream_content (applies encoder)
        ↓
    stream_text_async / stream_data_async
        ↓
    stream_text / stream_data (sync wrapper)

The `StreamingState` dataclass tracks mutable state across the streaming process:
- `tool_is_streaming`: Prevents duplicate tool call events when streaming deltas
- `ui_sources`: Collects source citations from tool results
- `model_response_message_id`: Links the response to Langfuse traces

## Stop Mechanism

Users can cancel streaming via `stop_streaming()`, which sets a cache key.
The `_agent_stop_streaming()` method checks this key periodically (every 2s)
and raises `StreamCancelException` to abort the generator.
"""

import asyncio
import dataclasses
import functools
import json
import logging
import os
import time
import uuid
from contextlib import AsyncExitStack, ExitStack
from io import BytesIO
from typing import AsyncGenerator, Callable, Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils.module_loading import import_string

from asgiref.sync import sync_to_async
from langfuse import get_client
from pydantic_ai import Agent, InstrumentationSettings, RunContext
from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ImageUrl,
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
    UserPromptPart,
)

from core.feature_flags.helpers import is_feature_enabled

from chat import models
from chat.agents.conversation import ConversationAgent, TitleGenerationAgent
from chat.agents.local_media_url_processors import (
    update_history_local_urls,
    update_local_urls,
)
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
from chat.tools.document_generic_search_rag import add_document_rag_search_tool_from_setting
from chat.tools.document_search_rag import add_document_rag_search_tool
from chat.tools.document_summarize import document_summarize
from chat.vercel_ai_sdk.core import events_v4, events_v5
from chat.vercel_ai_sdk.encoder import CURRENT_EVENT_ENCODER_VERSION, EventEncoder

# Keep at the top of the file to avoid mocking issues
document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

logger = logging.getLogger(__name__)

User = get_user_model()

CACHE_TIMEOUT = 30 * 60  # 30 minutes timeout
DOCUMENT_URL_PREFIX = "/media-key/"


@dataclasses.dataclass
class DocumentParsingResult:
    """Result marker for document parsing completion."""

    success: bool
    has_documents: bool


@dataclasses.dataclass
class StreamingState:
    """
    Mutable state shared across stream processing handlers.

    This dataclass is passed through the node handlers to track state that
    needs to persist across multiple yield points in the streaming process.

    Attributes:
        tool_is_streaming: Set to True when we receive ToolCallPartDelta events.
            When True, we skip emitting ToolCallPart in _handle_call_tools_node
            since the tool call was already streamed incrementally.
        ui_sources: Accumulates source citations from tool results (e.g., URLs
            from web search or RAG). These are appended to the final UI message.
        model_response_message_id: Set when the agent reaches the end node.
            Used to link the UI message to the Langfuse trace for scoring.
    """

    tool_is_streaming: bool = False
    ui_sources: List[SourceUIPart] = dataclasses.field(default_factory=list)
    model_response_message_id: Optional[str] = None


@dataclasses.dataclass
class ContextDeps:
    """Dependencies for context management."""

    conversation: models.ChatConversation
    user: User
    session: Optional[Dict] = None
    web_search_enabled: bool = False


def get_model_configuration(model_hrid: str):
    """Get the model configuration from settings."""
    try:
        return settings.LLM_CONFIGURATIONS[model_hrid]
    except KeyError as exc:
        raise ImproperlyConfigured(f"LLM model configuration '{model_hrid}' not found.") from exc


class AIAgentService:  # pylint: disable=too-many-instance-attributes
    """Service class for AI-related operations (Pydantic-AI edition)."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        conversation: models.ChatConversation,
        user,
        session=None,
        model_hrid=None,
        language=None,
    ):
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

        self._langfuse_available = settings.LANGFUSE_ENABLED
        self._store_analytics = self._langfuse_available and user.allow_conversation_analytics
        self.event_encoder = EventEncoder(CURRENT_EVENT_ENCODER_VERSION)  # We use v4 for now

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
            session=session,
            web_search_enabled=self._is_web_search_enabled,
        )

        self.conversation_agent = ConversationAgent(
            model_hrid=self.model_hrid,
            language=self.language,
            instrument=InstrumentationSettings(
                include_binary_content=self._store_analytics,
                include_content=self._store_analytics,
            )
            if self._langfuse_available
            else False,
            deps_type=ContextDeps,
        )
        add_document_rag_search_tool_from_setting(self.conversation_agent, self.user)

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
        cache.set(self._stop_cache_key, "1", timeout=CACHE_TIMEOUT)

    # --------------------------------------------------------------------- #
    # Async internals
    # --------------------------------------------------------------------- #

    async def _stream_content(
        self, messages: List[UIMessage], force_web_search: bool = False, encoder_fn: Callable = None
    ):
        """Common streaming logic with configurable encoder."""
        await self._clean()
        with ExitStack() as stack:
            if self._langfuse_available:
                span = stack.enter_context(get_client().start_as_current_span(name="conversation"))
                span.update_trace(user_id=str(self.user.sub), session_id=str(self.conversation.pk))

            async for event in self._run_agent(messages, force_web_search):
                if stream_text := encoder_fn(event):
                    yield stream_text

    async def stream_text_async(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return only the assistant text deltas (legacy text mode)."""
        async for chunk in self._stream_content(
            messages, force_web_search, encoder_fn=self.event_encoder.encode_text
        ):
            yield chunk

    async def stream_data_async(self, messages: List[UIMessage], force_web_search: bool = False):
        """Return Vercel-AI-SDK formatted events."""

        async for chunk in self._stream_content(
            messages, force_web_search, encoder_fn=self.event_encoder.encode
        ):
            yield chunk

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

    async def _prepare_agent_run(
        self, messages: List[UIMessage]
    ) -> Tuple[str, List, List, Dict[str, str], Dict[str, int], List, bool]:
        """
        Prepare all inputs needed before running the agent.

        This method handles the setup phase before the agent iteration loop:
        1. Loads and validates conversation history from pydantic_messages
        2. Pre-signs URLs for any local images in history (S3 signed URLs)
        3. Extracts user prompt, images, and documents from the last message
        4. Pre-signs URLs for input images
        5. Updates Langfuse trace with input (if analytics enabled)
        6. Checks if conversation already has documents in the vector store

        Returns:
            Tuple containing:
            - user_prompt: The text content of the user's message
            - input_images: List of images to send to the model
            - input_documents: List of documents to parse and store
            - image_key_mapping: Maps signed URLs back to storage keys (for saving)
            - usage: Token usage dict (initialized to zero)
            - history: Validated message history for the agent
            - conversation_has_documents: Whether RAG should be enabled
        """
        history = ModelMessagesTypeAdapter.validate_python(self.conversation.pydantic_messages)
        history = update_history_local_urls(
            self.conversation, history
        )  # presign URLs for local images

        user_prompt, input_images, input_documents = self._prepare_prompt(messages[-1])

        image_key_mapping = {}
        if input_images:
            # presign URLs for local images
            input_images = update_local_urls(
                self.conversation, input_images, updated_url=image_key_mapping
            )

        if self._langfuse_available:
            langfuse = get_client()
            langfuse.update_current_trace(
                input=user_prompt if self._store_analytics else "REDACTED"
            )

        usage = {"promptTokens": 0, "completionTokens": 0}

        conversation_has_documents = self._is_document_upload_enabled and (
            bool(self.conversation.collection_id)
            or bool(
                await models.ChatConversationAttachment.objects.filter(
                    conversation=self.conversation,
                    content_type__startswith="text/",
                ).aexists()
            )
        )
        return (
            user_prompt,
            input_images,
            input_documents,
            image_key_mapping,
            usage,
            history,
            conversation_has_documents,
        )

    def _setup_web_search(self, force_web_search: bool) -> bool:
        """Configure web search if forced. Returns whether web search is actually
        forced."""
        if not force_web_search:
            return False
        if not self._is_web_search_enabled:
            logger.warning("Web search is forced but the feature is disabled, ignoring.")
            return False

        web_search_tool_name = self.conversation_agent.get_web_search_tool_name()
        if not web_search_tool_name:
            logger.warning("Web search is forced but no web search tool is available, ignoring.")
            return False

        @self.conversation_agent.instructions
        def force_web_search_prompt() -> str:
            """Dynamic system prompt function to force web search."""
            return (
                f"You must call the {web_search_tool_name} tool before answering the user request."
            )

        return True

    async def _check_should_enable_rag(self, conversation_has_documents: bool) -> bool:
        """Check if RAG should be enabled based on existing documents."""

        if not self._is_document_upload_enabled:
            return False

        # Check for existing documents (any non-image attachment for this conversation)
        has_documents = await (
            models.ChatConversationAttachment.objects.filter(
                Q(conversion_from__isnull=True) | Q(conversion_from=""),
                conversation=self.conversation,
            )
            .exclude(content_type__startswith="image/")
            .aexists()
        )
        return conversation_has_documents or has_documents

    async def _process_agent_nodes(
        self, run, state: StreamingState, langfuse
    ) -> AsyncGenerator[events_v4.Event, None]:
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
          - Sets state.model_response_message_id for Langfuse linking
          - Yields StartStepPart with the message ID

        This method delegates to specialized handlers for each node type,
        passing the shared StreamingState to track cross-node state.

        The stop check (_agent_stop_streaming) is called for each node to
        allow cancel between processing steps.
        """
        async for node in run:
            await self._agent_stop_streaming()
            if Agent.is_user_prompt_node(node):
                # A user prompt node => The user has provided input
                pass

            elif Agent.is_model_request_node(node):
                # A model request node => agent is asking the model to generate a response
                async for event in self._handle_model_request_node(node, run.ctx, state):
                    yield event

            elif Agent.is_call_tools_node(node):
                # A handle-response node => The model returned some data,
                # potentially calls a tool
                async for event in self._handle_call_tools_node(node, run.ctx, state):
                    yield event

            elif Agent.is_end_node(node):
                # Once an End node is reached, the agent run is complete
                logger.debug("v: %s", dataclasses.asdict(node))
                yield self._handle_end_node(node, langfuse, state)

    async def _parse_input_documents(self, documents: List[BinaryContent | DocumentUrl]):
        """
        Parse and store input documents in the conversation's document store.

        This is the core document processing method that:
        1. Validates all document URLs belong to this conversation (security)
        2. Creates a vector store collection if one doesn't exist
        3. For each document:
             - Retrieves content from object storage (for DocumentUrl)
             - Parses the document (extracts text, chunks it)
             - Stores chunks with embeddings in the vector store
             - Creates a markdown attachment for non-text files (PDF → MD)

        Security: Documents are validated to ensure their URLs match the pattern
         `/media-key/{conversation_pk}/...` to prevent cross-conversation access.

        The actual parsing runs in a thread pool (asyncio.to_thread) to avoid
        blocking the event loop during potentially slow document processing.

        Args:
            documents: List of BinaryContent (inline data) or DocumentUrl (storage reference)

        Raises:
            ValueError: If document URL doesn't belong to this conversation
            ValueError: If external URLs are provided (not yet supported)
        """

        # Early external document URL rejection
        if any(
            not document.url.startswith(DOCUMENT_URL_PREFIX)
            for document in documents
            if isinstance(document, DocumentUrl)
        ):
            raise ValueError("External document URL are not accepted yet.")
        if any(
            not document.url.startswith(f"{DOCUMENT_URL_PREFIX}{self.conversation.pk}/")
            for document in documents
            if isinstance(document, DocumentUrl)
        ):
            raise ValueError("Document URL does not belong to the conversation.")

        document_store = document_store_backend(self.conversation.collection_id)
        if not document_store.collection_id:
            # Create a new collection for the conversation
            collection_id = document_store.create_collection(
                name=f"conversation-{self.conversation.pk}",
            )
            self.conversation.collection_id = str(collection_id)
            await self.conversation.asave(update_fields=["collection_id", "updated_at"])

        for document in documents:
            key = None
            if isinstance(document, DocumentUrl):
                if document.url.startswith(DOCUMENT_URL_PREFIX):
                    # Local file, retrieve from object storage
                    key = document.url[len(DOCUMENT_URL_PREFIX) :]
                    # Security check: ensure the document belongs to the conversation
                    if not key.startswith(f"{self.conversation.pk}/"):
                        raise ValueError("Document URL does not belong to the conversation.")
                    # Retrieve the document data
                    with default_storage.open(key, "rb") as file:
                        document_data = file.read()
                    # Run in thread to avoid blocking the event loop during parsing
                    parsed_content = await asyncio.to_thread(
                        document_store.parse_and_store_document,
                        name=document.identifier,
                        content_type=document.media_type,
                        content=document_data,
                        user_sub=self.user.sub,
                    )
                else:
                    # Remote URL
                    raise ValueError("External document URL are not accepted yet.")
            else:
                # Run in thread to avoid blocking the event loop during parsing
                parsed_content = await asyncio.to_thread(
                    document_store.parse_and_store_document,
                    name=document.identifier,
                    content_type=document.media_type,
                    content=document.data,
                    user_sub=self.user.sub,
                )

            if not document.media_type.startswith("text/"):
                md_attachment = await models.ChatConversationAttachment.objects.acreate(
                    conversation=self.conversation,
                    uploaded_by=self.user,
                    key=key or f"{self.conversation.pk}/attachments/{document.identifier}.md",
                    file_name=f"{document.identifier}.md",
                    content_type="text/markdown",
                    conversion_from=key,  # might be None
                )
                default_storage.save(md_attachment.key, BytesIO(parsed_content.encode("utf8")))
                md_attachment.upload_state = models.AttachmentStatus.READY
                await md_attachment.asave(update_fields=["upload_state", "updated_at"])

    def _prepare_prompt(  # noqa: PLR0912  # pylint: disable=too-many-branches
        self, message: UIMessage
    ) -> Tuple[str, List[BinaryContent | ImageUrl], List[BinaryContent]]:
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
            elif isinstance(content, ImageUrl):
                attachment_images.append(content)
            elif isinstance(content, DocumentUrl):
                attachment_documents.append(content)
            else:
                # Should never happen, but just in case
                raise ValueError(f"Unsupported UserContent type: {type(content)}")

        if attachment_audio:
            # Should be handled by the frontend, but just in case
            raise ValueError("Audio attachments are not supported in the current implementation.")
        if attachment_video:
            # Should be handled by the frontend, but just in case
            raise ValueError("Video attachments are not supported in the current implementation.")

        if len(user_prompt) != 1:
            raise ValueError(
                "User prompt must contain exactly one text part, "
                f"but got {len(user_prompt)} parts: {user_prompt}"
            )

        return user_prompt[0], attachment_images, attachment_documents

    def _setup_rag_tools(self) -> None:
        """Register RAG-related tools and instructions on the conversation agent."""
        add_document_rag_search_tool(self.conversation_agent)

        @self.conversation_agent.instructions
        def summarization_system_prompt() -> str:
            return (
                "When you receive a result from the summarization tool, you MUST return it "
                "directly to the user without any modification, paraphrasing, or additional "
                "summarization."
                "The tool already produces optimized summaries that should be presented "
                "verbatim."
                "You may translate the summary if required, but you MUST preserve all the "
                "information from the original summary."
                "You may add a follow-up question after the summary if needed."
            )

        # Inform the model (system-level) that documents are attached and available
        @self.conversation_agent.instructions
        def attached_documents_note() -> str:
            return (
                "[Internal context] User documents are attached to this conversation. "
                "Do not request re-upload of documents; consider them already available "
                "via the internal store."
            )

        @self.conversation_agent.tool(name="summarize", retries=2)
        @functools.wraps(document_summarize)
        async def summarize(ctx: RunContext, *args, **kwargs) -> ToolReturn:
            """Wrap the document_summarize tool to provide context and add the tool."""
            return await document_summarize(ctx, *args, **kwargs)

    async def _handle_input_documents(
        self,
        input_documents: List[BinaryContent | DocumentUrl],
        conversation_has_documents: bool,
        usage: Dict[str, int],
    ) -> AsyncGenerator[events_v4.Event | DocumentParsingResult, None]:
        """
        Handle document parsing with streaming progress events.

        This method processes documents attached to the user's message:
        1. Emits a ToolCallPart event to show "document_parsing" in the UI
        2. Calls _parse_input_documents() to store documents in the vector store
        3. Emits ToolResultPart with success/error status
        4. Yields a DocumentParsingResult marker as the final item

        The DocumentParsingResult pattern allows the caller to:
        - Yield all events to the stream in real-time
        - Check the final result to decide whether to continue or abort

        If document upload is disabled but documents are provided, they are
        silently ignored with a warning log.

        Yields:
            events_v4.Event: Tool call/result events for UI feedback
            DocumentParsingResult: Final marker with success status (must be last)
        """
        if not self._is_document_upload_enabled and input_documents:
            logger.warning("Document upload feature is disabled, ignoring input documents.")
            input_documents = []

        if not input_documents:
            yield DocumentParsingResult(success=True, has_documents=conversation_has_documents)
            return

        _tool_call_id = str(uuid.uuid4())
        yield events_v4.ToolCallPart(
            tool_call_id=_tool_call_id,
            tool_name="document_parsing",
            args={"documents": [{"identifier": doc.identifier} for doc in input_documents]},
        )

        try:
            await self._parse_input_documents(input_documents)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Error parsing input documents: %s", exc)
            yield (
                events_v4.ToolResultPart(
                    tool_call_id=_tool_call_id,
                    result={"state": "error", "error": str(exc)},
                )
            )
            yield (
                events_v4.FinishMessagePart(
                    finish_reason=events_v4.FinishReason.ERROR,
                    usage=events_v4.Usage(
                        prompt_tokens=usage["promptTokens"],
                        completion_tokens=usage["completionTokens"],
                    ),
                )
            )
            yield DocumentParsingResult(success=False, has_documents=conversation_has_documents)
            return
        yield events_v4.ToolResultPart(tool_call_id=_tool_call_id, result={"state": "done"})
        yield DocumentParsingResult(success=True, has_documents=True)

    async def _handle_non_streaming_response(self, node, run_ctx):
        result = await node.run(run_ctx)
        logger.debug("node.run result: %s", result)
        for part in result.model_response.parts:
            if isinstance(part, TextPart):
                if self._fake_streaming_delay:
                    for i in range(0, len(part.content), 4):
                        await self._agent_stop_streaming()
                        yield events_v4.TextPart(text=part.content[i : i + 4])
                        if os.environ.get("PYTHON_SERVER_MODE") == "async":
                            await asyncio.sleep(self._fake_streaming_delay)
                        else:
                            # sync mode needed for tests time manipulation
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
                logger.warning("Unknown part type: %s %s", type(part), dataclasses.asdict(part))

    async def _handle_streaming_response(self, node, run_ctx, state: StreamingState):
        async with node.stream(run_ctx) as request_stream:
            async for event in request_stream:
                await self._agent_stop_streaming()
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
                        state.tool_is_streaming = True
                        yield events_v4.ToolCallDeltaPart(
                            tool_call_id=event.delta.tool_call_id,
                            args_text_delta=event.delta.args_delta,
                        )
                    elif isinstance(event.delta, ThinkingPartDelta):
                        yield events_v4.ReasoningPart(reasoning=event.delta.content_delta)

    async def _handle_model_request_node(
        self, node, run_ctx, state: StreamingState
    ) -> AsyncGenerator[events_v4.Event, None]:
        """Handle model request node - streaming or non-streaming."""
        state.tool_is_streaming = False
        if not self._support_streaming:
            async for event in self._handle_non_streaming_response(node, run_ctx):
                yield event
        else:
            async for event in self._handle_streaming_response(node, run_ctx, state):
                yield event

    async def _handle_call_tools_node(
        self, node, run_ctx, state: StreamingState
    ) -> AsyncGenerator[events_v4.Event, None]:
        async with node.stream(run_ctx) as handle_stream:
            async for event in handle_stream:
                await self._agent_stop_streaming()
                logger.debug(
                    "Received request_stream event: %s, %s",
                    type(event),
                    dataclasses.asdict(event),
                )
                if isinstance(event, FunctionToolCallEvent):
                    if not state.tool_is_streaming:
                        yield events_v4.ToolCallPart(
                            tool_call_id=event.tool_call_id,
                            tool_name=event.part.tool_name,
                            args=json.loads(event.part.args) if event.part.args else {},
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
                                _new_source_ui = SourceUIPart(type="source", source=url_source)
                                state.ui_sources.append(_new_source_ui)
                                yield events_v4.SourcePart(**_new_source_ui.source.model_dump())
                        yield events_v4.ToolResultPart(
                            tool_call_id=event.tool_call_id, result=event.result.content
                        )

                    elif isinstance(event.result, RetryPromptPart):
                        yield events_v4.ToolResultPart(
                            tool_call_id=event.tool_call_id, result=event.result.content
                        )
                    else:
                        logger.warning(
                            "Unexpected tool result type: %s %s",
                            type(event.result),
                            dataclasses.asdict(event.result),
                        )

    def _handle_end_node(self, node, langfuse, state: StreamingState) -> events_v4.StartStepPart:
        """Handle end node - set message ID."""
        logger.debug("End node: %s", dataclasses.asdict(node))
        if state.model_response_message_id:
            logger.error("_model_response_message_id already set")
        state.model_response_message_id = (
            str(uuid.uuid4())
            if not self._langfuse_available
            else f"trace-{langfuse.get_current_trace_id()}"
        )
        return events_v4.StartStepPart(message_id=state.model_response_message_id)

    async def _finalize_conversation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        new_messages: list,
        run_output,
        usage: Dict[str, int],
        state: StreamingState,
        image_key_mapping: Dict[str, str],
    ) -> AsyncGenerator[events_v4.Event, None]:
        """
        Finalize the conversation after the agent run completes.

        This method handles all post-processing:
        1. Final stop check (allows late cancellation)
        2. Saves the conversation with:
           - New messages (user request + assistant response)
           - UI sources (citations from tools)
           - Token usage statistics
           - Image URL mappings (signed → unsigned for storage)
        3. Auto-generates a title after N user messages (if not manually set)
        4. Persists the conversation to the database
        5. Emits title update event (if generated)
        6. Updates Langfuse trace with final output
        7. Emits FinishMessagePart to signal stream completion

        Yields:
            DataPart: Title update notification (if title was generated)
            FinishMessagePart: Always emitted last to signal completion
        """
        await self._agent_stop_streaming(force_cache_check=True)

        # Prepare conversation update (save deferred until after potential title generation)
        await sync_to_async(self._prepare_update_conversation)(
            final_output=new_messages,
            usage=usage,
            ui_sources=state.ui_sources,
            model_response_message_id=state.model_response_message_id,
            image_key_mapping=image_key_mapping or None,
        )
        generated_title = None

        # Auto-generate title after N user messages if not manually set
        user_messages_count = sum(1 for msg in self.conversation.messages if msg.role == "user")

        should_generate_title = (
            user_messages_count == settings.AUTO_TITLE_AFTER_USER_MESSAGES
            and not self.conversation.title_set_by_user_at
        )

        if should_generate_title:
            if generated_title := await self._generate_title():
                self.conversation.title = generated_title

        # Persist conversation (including any generated title)
        await sync_to_async(self.conversation.save)()

        # Notify frontend about the title update
        if generated_title:
            yield events_v4.DataPart(
                data=[
                    {
                        "type": "conversation_metadata",
                        "conversationId": str(self.conversation.pk),
                        "title": generated_title,
                    }
                ]
            )
        if self._langfuse_available:
            langfuse = get_client()
            langfuse.update_current_trace(
                output=run_output if self._store_analytics else "REDACTED"
            )
            # Vercel finish message
        yield events_v4.FinishMessagePart(
            finish_reason=events_v4.FinishReason.STOP,
            usage=events_v4.Usage(
                prompt_tokens=usage["promptTokens"],
                completion_tokens=usage["completionTokens"],
            ),
        )

    async def _run_agent(  # pylint: disable=too-many-locals
        self,
        messages: List[UIMessage],
        force_web_search: bool = False,
    ) -> AsyncGenerator[events_v4.Event | events_v5.Event, None]:
        """Run the Pydantic AI agent and stream events."""
        if not messages or messages[-1].role != "user":
            return

        # Langfuse settings
        if self._langfuse_available:
            langfuse = get_client()
            langfuse.update_current_trace(
                session_id=str(self.conversation.pk),
                user_id=str(self.user.sub),
                metadata={
                    "user_fqdn": self.user.email.split("@")[-1],  # no need for security here
                },
            )
        else:
            langfuse = None

        (
            user_prompt,
            input_images,
            input_documents,
            image_key_mapping,
            usage,
            history,
            conversation_has_documents,
        ) = await self._prepare_agent_run(messages)

        doc_result = None
        async for item in self._handle_input_documents(
            input_documents, conversation_has_documents, usage
        ):
            if isinstance(item, DocumentParsingResult):
                doc_result = item
            else:
                yield item

        if doc_result is None or not doc_result.success:
            return

        conversation_has_documents = doc_result.has_documents

        await self._agent_stop_streaming(force_cache_check=True)
        self._setup_web_search(force_web_search)

        if await self._check_should_enable_rag(conversation_has_documents):
            self._setup_rag_tools()

        async with AsyncExitStack() as stack:
            # MCP servers (if any) can be initialized here
            mcp_servers = [await stack.enter_async_context(mcp) for mcp in get_mcp_servers()]

            # Help Mistral to prevent `Unexpected role 'user' after role 'tool'` error.
            if history and history[-1].kind == "request":
                if history[-1].parts and history[-1].parts[-1].part_kind == "tool-return":
                    history.append(ModelResponse(parts=[TextPart(content="ok")], kind="response"))

            async with self.conversation_agent.iter(
                [user_prompt] + input_images,
                message_history=history,  # history will pass through agent's history_processors
                deps=self._context_deps,
                toolsets=mcp_servers,
            ) as run:
                state = StreamingState()
                async for event in self._process_agent_nodes(run, state, langfuse):
                    yield event

                # Extract values from run before exiting the context manager
                new_messages = run.result.new_messages()
                run_output = run.result.output
                final_usage = run.usage()
                usage["promptTokens"] = final_usage.input_tokens
                usage["completionTokens"] = final_usage.output_tokens

        async for event in self._finalize_conversation(
            new_messages, run_output, usage, state, image_key_mapping
        ):
            yield event

    def _prepare_update_conversation(
        self,
        *,
        final_output: List[ModelRequest | ModelMessage],
        usage: Dict[str, int],
        ui_sources: Optional[List[SourceUIPart]] = None,
        model_response_message_id: str | None = None,
        image_key_mapping: Optional[Dict[str, str]] = None,
    ):  # pylint: disable=too-many-arguments
        """
        Save everything related to the conversation.

        Things to improve here:
         - The way we need to add the UI sources to the final output message.

        Args:
            final_output (List[ModelRequest | ModelMessage]): The final output from the agent.
            usage (Dict[str, int]): The token usage statistics.
            model_response_message_id (str | None): Message ID
            image_key_mapping (Dict[str, str] | None): Mapping of image id and S3 urls
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

        if image_key_mapping:
            for part in _merged_final_output_request.parts:
                if isinstance(part, UserPromptPart):
                    for content in part.content:
                        if isinstance(content, (ImageUrl, DocumentUrl)) and (
                            unsigned_url := image_key_mapping.get(content.url)
                        ):
                            content.url = unsigned_url

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

        final_output_json = json.loads(
            ModelMessagesTypeAdapter.dump_json(final_output).decode("utf-8")
        )
        logger.debug("final_output_json: %s", final_output_json)
        self.conversation.pydantic_messages += final_output_json

    async def _generate_title(self) -> str | None:
        """Generate a title for the conversation using LLM based on first messages."""

        # Build context from messages
        # Note: We intentionally use only msg.content for title generation.
        # Parts containing tool invocations or reasoning are excluded as they
        # don't contribute to a meaningful context here
        context = "\n".join(
            f"{msg.role}: {(msg.content or '')[:300]}"  # Limit content length per message
            for msg in self.conversation.messages
            if msg.content
        )

        language = self.language or settings.LANGUAGE_CODE
        prompt = (
            "Generate a concise title (3-5 words, max 100 characters) for this conversation.\n\n"
            "Requirements:\n"
            "- Capture the main topic or user intent\n"
            "- The title must be a simple string, no markdown\n"
            "- Help the user quickly identify the conversation\n"
            f"- Match the language of the user messages (default: {language})\n"
            "- Avoid the word 'summary' unless explicitly requested\n\n"
            "Output: Title text only, no quotes, labels, or explanation.\n\n"
            f"Conversation:\n{context}"
        )
        try:
            agent = TitleGenerationAgent()
            result = await agent.run(prompt)
            title = (result.output or "").strip()[:100]  # Enforce max length (conversation.title)
            logger.info("Generated title for conversation %s: %s", self.conversation.pk, title)
            return title if title else None
        except Exception as exc:  # pylint: disable=broad-except #noqa: BLE001
            logger.warning(
                "Failed to generate title for conversation %s: %s", self.conversation.pk, exc
            )
            return None
