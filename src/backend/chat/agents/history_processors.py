"""History processors for model message cleanup."""

import dataclasses
import logging

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from chat.document_context_builder import count_approx_tokens

from .summarize import SummarizationAgent

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PREFIX = (
    "[Conversation summary from previous turns] (context only, not a user request):\n"
)


@dataclasses.dataclass(frozen=True)
class HistoryCleanupResult:
    """Result of history cleanup, with optional generated summary."""

    history: list[ModelMessage]
    summary: str | None = None
    summary_checkpoint: int | None = None


def _stringify_message_content(content: object) -> str:
    """Convert part content to a plain text representation."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(item) for item in content if item is not None)
    return str(content)


def _format_exchanges_for_summary(messages: list[ModelMessage]) -> str:
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


async def conversation_summarization(
    messages: list[ModelMessage], *, max_tokens: int = 300, previous_summary: str | None = None
) -> str | None:
    """
    Summarize the conversation.
    """

    summarization_agent = SummarizationAgent()
    latest_summary = previous_summary
    exchanges = _format_exchanges_for_summary(messages)
    prompt = (
        "You are a conversation summarization assistant. Your role is to maintain\n"
        "a concise and accurate running summary of a conversation, "
        "omitting small talk and unrelated topics.\n\n"
        "Given the previous summary (if any) and the new exchanges provided,\n"
        "generate an updated summary that:\n\n"
        "- **Preserves** every key information, decisions, and important facts\n"
        "- **Integrates** the new exchanges in a coherent way\n"
        "- **Removes** redundant or non-essential details\n"
        "- **Maintains** the context needed for the conversation to continue\n"
        "- Is written in a neutral, factual, third-person style\n"
        "- Stays **concise** (5-10 lines maximum)\n\n"
        "## Previous Summary:\n"
        f"{latest_summary if latest_summary else ''}\n\n"
        "## New Exchanges:\n"
        f"{exchanges}\n\n"
        "Only answer with the updated summary, including the new exchanges "
        "information and the previous summary.\n\n"
        "## Updated Summary:\n"
    )
    logger.debug("Prompt for summarization: %s", prompt)
    logger.debug("Latest summary: %s", latest_summary)
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


def _history_cleanup_fallback(
    messages: list[ModelMessage], summary_checkpoint: int, context_messages: int
) -> HistoryCleanupResult:
    """Return the active history slice when summarization logic fails unexpectedly."""
    checkpoint = _safe_checkpoint(messages, summary_checkpoint)
    return HistoryCleanupResult(history=_active_history(messages, checkpoint, context_messages))


def _estimate_message_tokens(message: ModelMessage) -> int:
    """Estimate the token weight of one model message."""
    parts = getattr(message, "parts", []) or []
    if not parts:
        return 0

    part_tokens = 0
    for part in parts:
        content = getattr(part, "content", "")
        text = _stringify_message_content(content).strip()
        if text:
            part_tokens += count_approx_tokens(text)

        args = getattr(part, "args", "")
        if isinstance(args, str) and args.strip():
            part_tokens += count_approx_tokens(args)

    return part_tokens + (4 * len(parts)) + 4


def _estimate_history_tokens(messages: list[ModelMessage]) -> int:
    """Estimate token weight for a message list."""
    return sum(_estimate_message_tokens(message) for message in messages)


def _safe_checkpoint(messages: list[ModelMessage], summary_checkpoint: int) -> int:
    """Clamp the stored summary checkpoint to the current history size."""
    return max(0, min(summary_checkpoint, len(messages)))


def _active_start_index(
    messages: list[ModelMessage], summary_checkpoint: int, context_messages: int
) -> int:
    """Return where active history starts for a summary checkpoint."""
    checkpoint = _safe_checkpoint(messages, summary_checkpoint)
    return max(0, checkpoint - max(context_messages, 1))


def _active_history(
    messages: list[ModelMessage], summary_checkpoint: int, context_messages: int
) -> list[ModelMessage]:
    """Keep the last `context_messages` ModelMessage entries before the checkpoint."""
    active_start = _active_start_index(messages, summary_checkpoint, context_messages)
    active = messages[active_start:]
    if active:
        return active
    return messages[-1:] if messages else []


def build_active_history(
    messages: list[ModelMessage], summary_checkpoint: int, context_messages: int
) -> list[ModelMessage]:
    """Return the runtime history window for a summary checkpoint."""
    return _active_history(messages, summary_checkpoint, context_messages)


async def maybe_summarize_history(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    messages: list[ModelMessage],
    *,
    previous_summary: str | None = None,
    summary_checkpoint: int = 0,
    message_token_budget: int = 0,
    context_messages: int = 10,
    summary_max_tokens: int = 2048,
    allow_summary_generation: bool = True,
) -> HistoryCleanupResult:
    """
    Summarize when active history exceeds token budget.

    Called at the start of a new user turn against stored history from previous
    turns (the current user prompt is not in `messages` yet). That history
    normally ends on an assistant ModelResponse; use an even `context_messages`
    so the post-summary window starts on a user message.

    `summary_checkpoint` is the message index up to which `previous_summary`
    is valid. Runtime history keeps the last `context_messages` ModelMessage
    entries before the checkpoint so the model still has recent detailed context
    in addition to the summary.
    """
    try:
        checkpoint = _safe_checkpoint(messages, summary_checkpoint)
        active_history = _active_history(messages, checkpoint, context_messages)
        active_tokens = _estimate_history_tokens(active_history)
        logger.debug(
            (
                "maybe_summarize_history state: total_messages=%s checkpoint=%s "
                "active_messages=%s active_tokens=%s token_budget=%s"
            ),
            len(messages),
            checkpoint,
            len(active_history),
            active_tokens,
            message_token_budget,
        )

        if message_token_budget <= 0 or active_tokens <= message_token_budget:
            return HistoryCleanupResult(history=active_history)

        next_checkpoint = len(messages)
        if not allow_summary_generation or next_checkpoint <= checkpoint:
            return HistoryCleanupResult(history=active_history)

        summary_input = messages[checkpoint:next_checkpoint]
        logger.debug(
            "maybe_summarize_history summarizing messages %s:%s (%s message(s)).",
            checkpoint,
            next_checkpoint,
            len(summary_input),
        )
        summary = await conversation_summarization(
            summary_input,
            max_tokens=summary_max_tokens,
            previous_summary=previous_summary,
        )
        if not summary:
            logger.warning(
                "No updated summary generated, keeping previous summary and active context."
            )
            return HistoryCleanupResult(history=active_history)

        return HistoryCleanupResult(
            history=_active_history(messages, next_checkpoint, context_messages),
            summary=summary,
            summary_checkpoint=next_checkpoint,
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "History summarization failed, keeping active context: %s",
            exc,
            exc_info=True,
        )
        return _history_cleanup_fallback(messages, summary_checkpoint, context_messages)


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
    checkpoint = _safe_checkpoint(cleaned_history, summary_checkpoint)
    active_history = _active_history(cleaned_history, checkpoint, context_messages)
    return (
        _estimate_history_tokens(active_history) > message_token_budget
        and len(cleaned_history) > checkpoint
    )
