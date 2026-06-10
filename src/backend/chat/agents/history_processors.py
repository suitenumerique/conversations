"""Sliding window history processor for LLM conversation context management."""

import logging

from django.conf import settings

from pydantic_ai import ImageUrl
from pydantic_ai.messages import BinaryContent, ModelMessage, ModelRequest, UserPromptPart

from chat.tokens import (
    compute_conversation_budget as _compute_conversation_budget,
)
from chat.tokens import (
    count_approx_tokens,
)

# Conservative flat estimate per image part. Precise estimation is model-specific
# so a constant keeps the estimator model-agnostic
# while ensuring we never silently under-count images.
_IMAGE_TOKEN_ESTIMATE = 1500

logger = logging.getLogger(__name__)


def _stringify_message_content(content) -> str:
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


def _estimate_message_tokens(message: ModelMessage) -> int:
    parts = getattr(message, "parts", []) or []
    if not parts:
        return 0
    part_tokens = 0
    for part in parts:
        content = getattr(part, "content", "")
        if isinstance(content, (list, tuple)):
            for item in content:
                if isinstance(item, ImageUrl):
                    part_tokens += _IMAGE_TOKEN_ESTIMATE
                elif isinstance(item, BinaryContent) and item.media_type.startswith("image/"):
                    part_tokens += _IMAGE_TOKEN_ESTIMATE
                else:
                    text = _stringify_message_content(item).strip()
                    if text:
                        part_tokens += count_approx_tokens(text)
        else:
            text = _stringify_message_content(content).strip()
            if text:
                part_tokens += count_approx_tokens(text)
        args = getattr(part, "args", "")
        if isinstance(args, dict):
            part_tokens += count_approx_tokens(str(args))
        elif isinstance(args, str) and args.strip():
            part_tokens += count_approx_tokens(args)
    # Estimated overhead: ~4 tokens per part + ~4 tokens for message wrapper
    return part_tokens + (4 * len(parts)) + 4


def estimate_history_tokens(history: list[ModelMessage]) -> int:
    """Return the approximate token count for a list of messages."""
    return sum(_estimate_message_tokens(m) for m in history)


def _group_into_turns(history: list[ModelMessage]) -> list[list[ModelMessage]]:
    turns: list[list[ModelMessage]] = []
    current_turn: list[ModelMessage] = []
    for message in history:
        is_user_turn_start = isinstance(message, ModelRequest) and any(
            isinstance(p, UserPromptPart) for p in message.parts
        )
        if is_user_turn_start and current_turn:
            turns.append(current_turn)
            current_turn = []
        current_turn.append(message)
    if current_turn:
        turns.append(current_turn)
    return turns


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
            "Sliding window disabled: conversation budget is 0 "
            "(max_token_context=%d, security_buffer=%d, budget_ratio=%.2f).",
            max_token_context,
            security_buffer,
            budget_ratio,
        )
    return conversation_budget


def apply_sliding_window(
    history: list[ModelMessage],
    conversation_budget: int,
) -> tuple[list[ModelMessage], bool]:
    """Drop oldest turns until history fits within conversation_budget tokens.

    Returns the (possibly trimmed) history and a flag indicating whether trimming occurred.
    """
    if conversation_budget == 0 or not history:
        return history, False
    if estimate_history_tokens(history) <= conversation_budget:
        return history, False
    turns = _group_into_turns(history)
    was_trimmed = False
    # len(turns) > 1 guarantees we never drop the last turn (the current exchange)
    while (
        len(turns) > 1
        and estimate_history_tokens([m for t in turns for m in t]) > conversation_budget
    ):
        turns.pop(0)
        was_trimmed = True
    return [m for turn in turns for m in turn], was_trimmed
