"""History processors for model message cleanup."""

import dataclasses
import logging

from django.conf import settings

from pydantic_ai import ImageUrl
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from chat.constants import IMAGE_MIME_PREFIX
from chat.tokens import compute_conversation_budget as _compute_conversation_budget
from chat.tokens import count_approx_tokens
from chat.tools.descriptions import CONVERSATION_SUMMARY_TOOL_DESCRIPTION

from .summarize import SummarizationAgent

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PREFIX = (
    "[Conversation summary from previous turns] (context only, not a user request):\n"
)

_TOKENS_PER_PART_OVERHEAD = 4  # framing/delimiters per message part
_TOKENS_PER_MESSAGE_OVERHEAD = 4  # per-message envelope

# Conservative flat estimate per image part. Precise estimation is model-specific,
# so a constant keeps the estimator model-agnostic while ensuring we never silently
# under-count images.
_IMAGE_TOKEN_ESTIMATE = 1500


class SummarizationRequiredError(Exception):
    """A summary was required to fit the token budget but could not be generated."""


def _stringify_message_content(content: object) -> str:
    """Convert part content to a plain text representation."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return " ".join(_stringify_message_content(c) for c in content)
    if hasattr(content, "content"):
        return _stringify_message_content(content.content)
    if hasattr(content, "text"):
        return _stringify_message_content(content.text)
    return ""


def _format_exchanges_for_summary(messages: list[ModelMessage]) -> str:
    """Render user/assistant turns as `Role: text` lines for the summary prompt."""
    lines = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            role = "User"
            parts = (p for p in msg.parts if isinstance(p, UserPromptPart))
        elif isinstance(msg, ModelResponse):
            role = "Assistant"
            parts = (p for p in msg.parts if isinstance(p, TextPart))
        else:
            continue

        for part in parts:
            content = part.content
            text = _stringify_message_content(content).strip()
            if text:
                lines.append(f"{role}: {text}")
    return "\n".join(lines)


async def summarize_conversation(
    messages: list[ModelMessage], *, max_tokens: int, previous_summary: str | None = None
) -> str | None:
    """Generate an updated running summary, folding `previous_summary` into `messages`.

    Returns the new summary text, or None when the model produces nothing or the
    summarization call fails.
    """
    summarization_agent = SummarizationAgent()
    latest_summary = previous_summary or ""
    exchanges = _format_exchanges_for_summary(messages)
    prompt = (CONVERSATION_SUMMARY_TOOL_DESCRIPTION + "\n\n").format(
        exchanges=exchanges, latest_summary=latest_summary
    )
    logger.debug("Prompt for summarization: %s", prompt)
    try:
        resp = await summarization_agent.run(
            prompt,
            model_settings={"max_tokens": max_tokens},
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning("Conversation summarization failed: %s", exc, exc_info=True)
        return None
    updated_summary = (resp.output or "").strip()
    logger.debug("Updated summary: %s", updated_summary)
    return updated_summary or None


def _latest_tool_call_ids(messages: list[ModelMessage]) -> set[str]:
    """Return the tool_call_ids of the most recent assistant tool-call turn."""
    for message in reversed(messages):
        if not isinstance(message, ModelResponse):
            continue
        response_tool_calls = [
            part.tool_call_id
            for part in message.parts
            if isinstance(part, ToolCallPart) and isinstance(part.tool_call_id, str)
        ]
        if response_tool_calls:
            return set(response_tool_calls)
    return set()


def _clean_request_parts(parts: list, latest_tool_call_ids: set[str]) -> list:
    """Replace stale tool returns with a compact placeholder, keeping the latest cycle."""
    kept_parts = []
    for part in parts:
        if not isinstance(part, ToolReturnPart):
            kept_parts.append(part)
            continue
        if part.tool_call_id in latest_tool_call_ids:
            kept_parts.append(part)
            continue
        tool_name = getattr(part, "tool_name", None) or "unknown_tool"
        kept_parts.append(
            ToolReturnPart(
                tool_call_id=part.tool_call_id,
                tool_name=tool_name,
                content=f"<{tool_name} response compacted>",
            )
        )
    return kept_parts


def clean_tool_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Compact old tool returns while preserving the latest tool cycle."""
    latest_tool_call_ids = _latest_tool_call_ids(messages)
    cleaned_history: list[ModelMessage] = []

    for message in messages:
        if isinstance(message, ModelRequest):
            kept_parts = _clean_request_parts(message.parts, latest_tool_call_ids)
            if kept_parts:
                cleaned_history.append(dataclasses.replace(message, parts=kept_parts))
            continue

        cleaned_history.append(message)

    return cleaned_history


def safe_clean_tool_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Compact tool history, falling back to the input on unexpected errors."""
    try:
        return clean_tool_history(messages)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "Tool history cleanup failed, using raw history: %s",
            exc,
            exc_info=True,
        )
        return messages


def _estimate_text_tokens(value: object) -> int:
    """Count tokens for a stringifiable value, ignoring blank content."""
    text = _stringify_message_content(value).strip()
    return count_approx_tokens(text) if text else 0


def _estimate_item_tokens(item: object) -> int:
    """Count tokens for one content item, flat-rating images."""
    if isinstance(item, ImageUrl):
        return _IMAGE_TOKEN_ESTIMATE
    if isinstance(item, BinaryContent) and item.media_type.startswith(IMAGE_MIME_PREFIX):
        return _IMAGE_TOKEN_ESTIMATE
    return _estimate_text_tokens(item)


def _estimate_content_tokens(content: object) -> int:
    """Count tokens for a part's content, whether a scalar or a sequence."""
    if isinstance(content, (list, tuple)):
        return sum(_estimate_item_tokens(item) for item in content)
    return _estimate_text_tokens(content)


def _estimate_args_tokens(args: object) -> int:
    """Count tokens for a tool-call part's args."""
    if isinstance(args, dict):
        return count_approx_tokens(str(args))
    if isinstance(args, str) and args.strip():
        return count_approx_tokens(args)
    return 0


def _estimate_part_tokens(part: object) -> int:
    """Count tokens for one message part: its content plus any tool-call args."""
    return _estimate_content_tokens(getattr(part, "content", "")) + _estimate_args_tokens(
        getattr(part, "args", "")
    )


def _estimate_message_tokens(message: ModelMessage) -> int:
    """Estimate the token weight of one model message."""
    parts = getattr(message, "parts", []) or []
    if not parts:
        return 0

    part_tokens = sum(_estimate_part_tokens(part) for part in parts)
    return part_tokens + (_TOKENS_PER_PART_OVERHEAD * len(parts)) + _TOKENS_PER_MESSAGE_OVERHEAD


def _estimate_history_tokens(messages: list[ModelMessage]) -> int:
    """Estimate token weight for a message list."""
    return sum(_estimate_message_tokens(message) for message in messages)


def _safe_checkpoint(messages: list[ModelMessage], summary_checkpoint: int) -> int:
    """Clamp the stored summary checkpoint to the current history size."""
    return max(0, min(summary_checkpoint, len(messages)))


def build_active_history(
    messages: list[ModelMessage], summary_checkpoint: int, context_messages: int
) -> list[ModelMessage]:
    """Trim history to the runtime window: the last `context_messages` entries
    before the checkpoint, plus everything after it.

    Pure list-slicing, no LLM. This is the history the model actually sees for
    the current turn; the summarized prefix (everything before the window) is
    represented by the persisted summary instead. Never returns empty while
    `messages` is non-empty.
    """
    checkpoint = _safe_checkpoint(messages, summary_checkpoint)
    active_start = max(0, checkpoint - max(context_messages, 1))
    active = messages[active_start:]
    if active:
        return active
    return messages[-1:] if messages else []


def _active_window(
    messages: list[ModelMessage], summary_checkpoint: int, context_messages: int
) -> tuple[int, list[ModelMessage], int]:
    """Return (clamped checkpoint, active-history slice, its token estimate)."""
    checkpoint = _safe_checkpoint(messages, summary_checkpoint)
    active_history = build_active_history(messages, checkpoint, context_messages)
    return checkpoint, active_history, _estimate_history_tokens(active_history)


async def generate_history_summary(
    messages: list[ModelMessage],
    *,
    previous_summary: str | None = None,
    summary_checkpoint: int = 0,
    summary_max_tokens: int = 2048,
) -> tuple[str, int]:
    """Summarize everything after the checkpoint; return (summary, new_checkpoint).

    Called by the Celery task once `should_generate_conversation_summary` has
    confirmed the history is over budget. Summarizes `messages[checkpoint:]`,
    folding in `previous_summary`, and returns the text plus the advanced
    checkpoint (the full message count). Raises `SummarizationRequiredError`
    when the model yields nothing, so the task retries rather than persisting an
    empty summary.
    """
    checkpoint = _safe_checkpoint(messages, summary_checkpoint)
    next_checkpoint = len(messages)
    summary_input = messages[checkpoint:next_checkpoint]
    logger.debug(
        "generate_history_summary summarizing messages %s:%s (%s message(s)).",
        checkpoint,
        next_checkpoint,
        len(summary_input),
    )
    summary = await summarize_conversation(
        summary_input,
        max_tokens=summary_max_tokens,
        previous_summary=previous_summary,
    )
    if not summary:
        raise SummarizationRequiredError(
            "Summarization produced no output for the over-budget history "
            f"({len(summary_input)} message(s) after checkpoint {checkpoint})."
        )
    return summary, next_checkpoint


def resolve_conversation_budget(configuration) -> int:
    """Return the token budget for conversation history given an LLM configuration."""
    max_token_context = getattr(configuration, "max_token_context", None)
    if max_token_context is None:
        max_token_context = settings.DEFAULT_MAX_TOKEN_CONTEXT
    security_buffer = settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS
    budget_ratio = settings.DOCUMENT_CONTEXT_BUDGET_RATIO
    system_prompt = getattr(configuration, "system_prompt", None)
    system_prompt_tokens = count_approx_tokens(system_prompt) if system_prompt else 0
    conversation_budget = max(
        _compute_conversation_budget(max_token_context, budget_ratio, security_buffer)
        - system_prompt_tokens,
        0,
    )
    if conversation_budget == 0 and max_token_context > 0:
        logger.warning(
            "Summarization is disabled: conversation budget is 0 "
            "(max_token_context=%d, security_buffer=%d, budget_ratio=%.2f).",
            max_token_context,
            security_buffer,
            budget_ratio,
        )
    return conversation_budget


def should_generate_conversation_summary(
    messages: list[ModelMessage],
    *,
    summary_checkpoint: int = 0,
    message_token_budget: int = 0,
    context_messages: int = 10,
) -> bool:
    """Return True when active history exceeds budget and new messages can be summarized."""
    if message_token_budget <= 0:
        return False

    cleaned_history = safe_clean_tool_history(messages)
    checkpoint, _active, active_tokens = _active_window(
        cleaned_history, summary_checkpoint, context_messages
    )
    return active_tokens > message_token_budget and len(cleaned_history) > checkpoint
