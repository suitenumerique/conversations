"""Token counting and budget utilities shared across chat modules."""

import functools
import logging

import tiktoken

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _get_token_encoding():
    return tiktoken.get_encoding("cl100k_base")


def count_approx_tokens(text: str) -> int:
    """Estimate token count using tiktoken."""
    if not text:
        return 0
    try:
        return len(_get_token_encoding().encode(text))
    except Exception:  # pylint: disable=broad-except #noqa: BLE001
        logger.warning("Failed to estimate tokens with tiktoken, falling back to heuristic.")
        non_space_chars = len("".join(text.split()))
        if non_space_chars == 0:
            return 0
        return (non_space_chars + 2) // 3


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Cut `text` down to at most `max_tokens` tokens, as counted by count_approx_tokens."""
    if count_approx_tokens(text) <= max_tokens:
        return text
    try:
        encoding = _get_token_encoding()
        return encoding.decode(encoding.encode(text)[:max_tokens])
    except Exception:  # pylint: disable=broad-except #noqa: BLE001
        logger.warning("Failed to truncate with tiktoken, falling back to heuristic.")
        # Mirror the heuristic of count_approx_tokens: about 3 characters per token.
        return text[: max_tokens * 3]


def compute_document_budget(
    max_token_context: int, budget_ratio: float, security_buffer: int
) -> int:
    """Return the token budget for document inlining."""
    return max(int(max_token_context * budget_ratio) - security_buffer, 0)


def compute_conversation_budget(
    max_token_context: int, budget_ratio: float, security_buffer: int
) -> int:
    """Return the token budget for conversation history."""
    return max(int(max_token_context * (1 - budget_ratio)) - security_buffer, 0)
