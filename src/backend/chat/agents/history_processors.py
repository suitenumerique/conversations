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


def _extract_latest_summary_from_instructions(messages: list[ModelMessage]) -> str | None:
    """Extract the latest injected summary from request instructions, if any."""
    marker = f"{SUMMARY_SYSTEM_PREFIX}"
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        instructions = getattr(message, "instructions", None)
        if not isinstance(instructions, str):
            continue
        marker_index = instructions.rfind(marker)
        if marker_index == -1:
            continue
        return instructions[marker_index + len(marker) :].strip() or None
    return None


async def conversation_summarization(
    messages: list[ModelMessage], *, max_tokens: int = 300, previous_summary: str | None = None
) -> str | None:
    """
    Summarize the conversation.
    """

    summarization_agent = SummarizationAgent()
    latest_summary = previous_summary or _extract_latest_summary_from_instructions(messages)
    prompt = (
        "You are a conversation summarization assistant. Your role is to maintain\n"
        "a concise and accurate running summary of a conversation, "
        "omitting small talk and unrelated topics.\n\n"
        "Given the previous summary (if any) and the new exchanges provided,\n"
        "generate an updated summary that:\n\n"
        "- **Preserves** key information, decisions, and important facts\n"
        "- **Integrates** the new exchanges in a coherent way\n"
        "- **Removes** redundant or non-essential details\n"
        "- **Maintains** the context needed for the conversation to continue\n"
        "- Is written in a neutral, factual, third-person style\n"
        "- Stays **concise** (5-10 lines maximum)\n\n"
        "## Previous Summary:\n"
        f"{latest_summary if latest_summary else ''}\n\n"
        "## New Exchanges:\n"
        f"{messages}\n\n"
        "Only answer with the updated summary, including the new exchanges "
        "information and the previous summary."
        "## Updated Summary:\n"
    )
    logger.debug("Prompt for summarization: %s", prompt)
    logger.debug("Latest summary: %s", latest_summary)
    try:
        resp = await summarization_agent.run(
            prompt,
            # message_history=messages,
            model_settings={"max_tokens": max_tokens},
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning("Conversation summarization failed: %s", exc, exc_info=True)
        return None
    updated_summary = (resp.output or "").strip()
    logger.debug("Updated summary: %s", updated_summary)
    return updated_summary or None


def _replace_message_parts(message: ModelMessage, kept_parts: list):
    """
    Return a message clone with updated parts across pydantic-ai versions.

    Depending on the installed pydantic-ai version, messages can expose:
    - `model_copy(update=...)` (pydantic model style), or
    - dataclass semantics (no `model_copy`).
    """
    if hasattr(message, "model_copy"):
        return message.model_copy(update={"parts": kept_parts})
    return dataclasses.replace(message, parts=kept_parts)


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
            UserPromptPart(content=[f"Tool responded with data: <{tool_name} response>"])
        )
    return kept_parts


def _clean_response_parts(parts: list, latest_tool_call_ids: set[str]) -> list:
    kept_parts = []
    for part in parts:
        if not isinstance(part, ToolCallPart):
            kept_parts.append(part)
            continue
        if part.tool_call_id in latest_tool_call_ids:
            kept_parts.append(part)
            continue
        tool_name = getattr(part, "tool_name", None) or "unknown_tool"
        args = getattr(part, "args", None)
        if args:
            kept_parts.append(TextPart(content=f"Tool called: {tool_name} with args: {args}"))
            continue
        kept_parts.append(TextPart(content=f"Tool called: {tool_name}"))
    return kept_parts


def _count_turns(messages: list[ModelMessage]) -> int:
    """Count turns as user requests only (stable across tool sub-messages)."""
    return sum(
        1
        for message in messages
        if isinstance(message, ModelRequest)
        and any(isinstance(part, UserPromptPart) for part in message.parts)
    )


def _take_last_turns(messages: list[ModelMessage], turns: int) -> list[ModelMessage]:
    """Return only the last N turns from a chronological message list."""
    if turns <= 0:
        return []

    user_request_indexes = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, ModelRequest)
        and any(isinstance(part, UserPromptPart) for part in message.parts)
    ]
    if not user_request_indexes:
        return messages
    if len(user_request_indexes) <= turns:
        return messages

    start_index = user_request_indexes[-turns]
    return messages[start_index:]


async def history_cleanup(
    messages: list[ModelMessage],
    *,
    previous_summary: str | None = None,
    summary_interval_turns: int = 3,
    context_turns: int = 2,
) -> HistoryCleanupResult:
    """
    Keep only the latest tool cycle in full detail.

    Strategy:
    - Keep all non-tool parts from every message.
    - Keep tool-call/tool-return parts for the latest tool cycle.
    - Replace older tool-call/tool-return parts with compact text traces.
    - Drop messages that become empty after filtering.

    This limits context growth while preserving useful recent tool details.
    """
    logger.debug("History before cleanup: %s", messages)

    latest_tool_call_ids = _latest_tool_call_ids(messages)

    cleaned_history: list[ModelMessage] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            kept_parts = _clean_request_parts(message.parts, latest_tool_call_ids)
            if kept_parts:
                cleaned_history.append(_replace_message_parts(message, kept_parts))
            continue

        if isinstance(message, ModelResponse):
            kept_parts = _clean_response_parts(message.parts, latest_tool_call_ids)
            if kept_parts:
                cleaned_history.append(_replace_message_parts(message, kept_parts))
            continue

        cleaned_history.append(message)

    logger.debug("History after cleanup: %s", cleaned_history)

    turns_count = _count_turns(cleaned_history)
    summary_interval_turns = max(summary_interval_turns, 1)
    context_turns = max(context_turns, 1)
    logger.debug("Number of turns in cleaned history: %s", turns_count)
    if turns_count > 0 and turns_count % summary_interval_turns == 0:
        logger.debug("Summarizing conversation...")
        # Only summarize the new slice since last checkpoint, then merge
        # with previous_summary inside conversation_summarization.
        summary_input = _take_last_turns(cleaned_history, turns=summary_interval_turns)
        summary = await conversation_summarization(
            summary_input,
            max_tokens=2048,
            previous_summary=previous_summary,
        )
        if not summary:
            logger.warning(
                "No updated summary generated, keeping previous summary and current context window."
            )
            if previous_summary:
                return HistoryCleanupResult(
                    history=_take_last_turns(cleaned_history, turns=context_turns),
                    summary=previous_summary,
                )
            return HistoryCleanupResult(history=cleaned_history)
        logger.debug("Summary: %s", summary)
        # Keep detailed history in DB, but trim runtime context once summary is generated.
        return HistoryCleanupResult(
            history=_take_last_turns(cleaned_history, turns=context_turns), summary=summary
        )

    if previous_summary:
        return HistoryCleanupResult(history=_take_last_turns(cleaned_history, turns=context_turns))

    return HistoryCleanupResult(history=cleaned_history)


# check for summary generation need to know if the current
# turn should trigger a frontend summary event
def should_generate_conversation_summary(
    messages: list[ModelMessage], *, summary_interval_turns: int = 3
) -> bool:
    """Return True when the current turn should trigger summary regeneration."""
    turns_count = _count_turns(messages)
    summary_interval_turns = max(summary_interval_turns, 1)
    return turns_count > 0 and turns_count % summary_interval_turns == 0
