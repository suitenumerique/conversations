"""
Util classes for  main agent.
"""

import dataclasses
from typing import Dict, List, Optional

from django.contrib.auth import get_user_model

from chat import models
from chat.ai_sdk_types import SourceUrlUIPart

User = get_user_model()


@dataclasses.dataclass
class DocumentParsingResult:
    """Result marker for document parsing completion."""

    success: bool
    has_documents: bool


@dataclasses.dataclass
class PreparedHistory:
    """Result marker carrying the prepared (trimmed) history out of the summary phase."""

    history: List


@dataclasses.dataclass
class PersistedTurn:
    """What is left to emit once a finished turn has been written to the database.

    The turn is persisted by the producer task, as soon as the run ends, so a
    client that disconnects while the queued frames are still draining cannot
    take the finished turn with it. The frames that persistence produces -- the
    cooldown, the generated title, the CO2 annotation -- have to outlive that
    call and reach the consumer, so they are parked here.
    """

    generated_title: Optional[str] = None
    cooldown_seconds: int = 0
    message_co2_impact: float = 0


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
        persisted_turn: Set once a completed turn has been written to the
            database, carrying the frames the consumer still has to emit.
    """

    tool_is_streaming: bool = False
    ui_sources: List[SourceUrlUIPart] = dataclasses.field(default_factory=list)
    model_response_message_id: Optional[str] = None
    persisted_turn: Optional["PersistedTurn"] = None


@dataclasses.dataclass
class ContextDeps:
    """Dependencies for context management."""

    conversation: models.ChatConversation
    user: User
    session: Optional[Dict] = None
    web_search_enabled: bool = False


@dataclasses.dataclass
class ImagePostRunActions:
    """Per-turn instructions for image-URL surgery on the persisted messages.

    Two orthogonal concerns flow through here:

    - ``rewrite``: presigned URL -> durable storage form. Conversation
      attachments come in as local ``/media-key/...`` URLs from the frontend,
      get presigned for the LLM by ``update_local_urls``, and must be
      rewritten back to the local form before the turn is persisted to
      ``pydantic_messages`` (otherwise reload would carry an expired URL).
    - ``drop``: presigned URLs that must NOT be persisted at all. Project
      image pins live here: they are re-derived fresh from
      ``project.attachments`` on every turn, so persisting them would
      duplicate one image per turn in history and break playback once the
      presigned URL expires.

    The two are kept as separate fields (rather than a single dict with a
    sentinel value) so each callsite reads as the action it represents.
    """

    rewrite: Dict[str, str] = dataclasses.field(default_factory=dict)
    drop: set = dataclasses.field(default_factory=set)
