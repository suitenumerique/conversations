"""What a finished turn writes to its conversation: messages, usage, title."""

import json
from typing import List, Optional

from django.conf import settings

import structlog
from pydantic_ai.messages import (
    DocumentUrl,
    ImageUrl,
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)

from core.log_fields import safe_error_fields

from chat import models
from chat.agents.conversation import TitleGenerationAgent
from chat.ai_sdk_types import SourceUrlUIPart
from chat.clients.pydantic_ui_message_converter import (
    attach_tool_charts,
    merge_by_kind,
    model_message_to_ui_message,
)
from chat.clients.schema import ImagePostRunActions
from chat.turn.usage import AgentUsage

# Not __name__: "chat.turn.*" would nest under the "chat.turn" turn-trace
# logger, whose level and log filter are meant to cover the turn trace alone.
# Keep the name these lines had before the split.
logger = structlog.get_logger("chat.clients.pydantic_ai")


def truncation_annotation() -> dict[str, bool]:
    """The flag marking a response cut off at the output token limit.

    Streamed as a v4 message annotation, which the v4->v5 encoder folds into the
    `finish` message metadata, and persisted directly in the message metadata.
    One source of truth so the two never drift.
    """
    return {"truncated": True}


def apply_image_actions(
    final_output: List[ModelRequest | ModelMessage],
    image_actions: Optional[ImagePostRunActions],
) -> None:
    """Rewrite or drop image URLs in every ``UserPromptPart`` of ``final_output``.

    Mutates in place: the merged views, the UI-message conversion, and
    the ``pydantic_messages`` JSON dump downstream all read from
    ``final_output``'s parts, so a single in-place pass covers every
    persistence path. Replacing ``part.content`` with a new list (rather
    than mutating it during iteration) keeps Pydantic-AI's validation
    happy.
    """
    if not image_actions or not (image_actions.rewrite or image_actions.drop):
        return
    for msg in final_output:
        if not isinstance(msg, ModelRequest):
            continue
        for part in msg.parts:
            if not isinstance(part, UserPromptPart):
                continue
            part.content = _apply_to_content(part.content, image_actions)


def _apply_to_content(contents, image_actions: ImagePostRunActions) -> list:
    """One part's content as a new list, its image URLs rewritten or dropped."""
    new_content = []
    for content in contents:
        if isinstance(content, (ImageUrl, DocumentUrl)):
            if content.url in image_actions.drop:
                continue
            if rewritten := image_actions.rewrite.get(content.url):
                content.url = rewritten
        new_content.append(content)
    return new_content


def prepare_update_conversation(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    conversation: models.ChatConversation,
    *,
    final_output: List[ModelRequest | ModelMessage],
    usage: AgentUsage,
    ui_sources: Optional[List[SourceUrlUIPart]] = None,
    model_response_message_id: str | None = None,
    image_actions: Optional[ImagePostRunActions] = None,
    is_truncated: bool,
    question_stored: bool,
) -> AgentUsage:
    """
    Save everything related to the conversation.

    Things to improve here:
     - The way we need to add the UI sources to the final output message.

    Args:
        conversation (ChatConversation): The conversation to update (not saved here).
        final_output (List[ModelRequest | ModelMessage]): The final output from the agent.
        usage (AgentUsage): Token and CO2 usage of this turn only.
        model_response_message_id (str | None): Message ID
        ui_sources (List[SourceUrlUIPart]): Optional UI sources to include.
        image_actions (ImagePostRunActions | None): Per-turn image-URL
        surgery to apply before persistence (rewrite presigned URLs back
        to durable form for in-message images, drop pinned project
        images outright). See ``ImagePostRunActions`` for details.
        is_truncated (bool): Whether the response stopped at the output token limit.
        question_stored (bool): Whether this turn's question is already in
        ``conversation.messages``.

    Returns:
        AgentUsage: The conversation's usage total, this turn included.
    """
    apply_image_actions(final_output, image_actions)

    _merged_final_output_request, _merged_final_output_message = merge_by_kind(final_output)

    _output_ui_message = model_message_to_ui_message(_merged_final_output_message)
    attach_tool_charts(_output_ui_message, _merged_final_output_request)
    if ui_sources:
        _output_ui_message.parts += ui_sources
    if model_response_message_id:
        _output_ui_message.id = model_response_message_id
    else:
        logger.warning("model_response_message_id_missing")

    if usage.co2_impact:
        _output_ui_message.metadata = {
            **(_output_ui_message.metadata or {}),
            "co2_impact": usage.co2_impact,
        }

    if is_truncated:
        _output_ui_message.metadata = {
            **(_output_ui_message.metadata or {}),
            **truncation_annotation(),
        }

    conversation_usage = usage + AgentUsage.from_stored(conversation.agent_usage)
    conversation.agent_usage = conversation_usage.to_stored()

    # Tracked rather than read off the list: a question-only turn folded in
    # earlier also leaves a trailing user message, and taking that as "this
    # turn's question is stored" dropped the question being answered here.
    if not question_stored:
        _request_ui_message = model_message_to_ui_message(_merged_final_output_request)
        # None when the request holds nothing renderable (system prompt or
        # tool return only): there is no user bubble to rebuild.
        if _request_ui_message:
            conversation.messages += [_request_ui_message]
    conversation.messages += [_output_ui_message]

    final_output_json = json.loads(ModelMessagesTypeAdapter.dump_json(final_output).decode("utf-8"))
    conversation.pydantic_messages += final_output_json
    return conversation_usage


async def generate_title_if_needed(
    conversation: models.ChatConversation, language: str | None
) -> str | None:
    """Generate and set title if auto-title conditions are met."""
    user_messages_count = sum(1 for msg in conversation.messages if msg.role == "user")
    if user_messages_count != settings.AUTO_TITLE_AFTER_USER_MESSAGES:
        return None
    if conversation.title_set_by_user_at:
        return None
    title = await generate_title(conversation, language)
    if title:
        conversation.title = title
    return title


async def generate_title(conversation: models.ChatConversation, language: str | None) -> str | None:
    """Generate a title for the conversation using LLM based on first messages."""

    # Build context from messages
    # Note: We intentionally use only msg.content for title generation.
    # Parts containing tool invocations or reasoning are excluded as they
    # don't contribute to a meaningful context here
    context = "\n".join(
        f"{msg.role}: {(msg.content or '')[:300]}"  # Limit content length per message
        for msg in conversation.messages
        if msg.content
    )

    language = language or settings.LANGUAGE_CODE
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
        logger.info("title_generated", conversation_id=conversation.pk)
        return title if title else None
    except Exception as exc:  # pylint: disable=broad-except #noqa: BLE001
        logger.warning(
            "title_generation_failed", conversation_id=conversation.pk, **safe_error_fields(exc)
        )
        return None
