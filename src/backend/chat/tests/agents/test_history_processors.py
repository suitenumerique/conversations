"""Tests for chat.agents.history_processors."""

import logging

from django.test import override_settings

from pydantic_ai import ImageUrl
from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from chat.agents.history_processors import (
    _IMAGE_TOKEN_ESTIMATE,
    _estimate_message_tokens,
    _group_into_turns,
    _stringify_message_content,
    apply_sliding_window,
    estimate_history_tokens,
    resolve_conversation_budget,
)
from chat.tokens import count_approx_tokens

# ── helpers ──────────────────────────────────────────────────────────────────


def user_msg(text: str) -> ModelRequest:
    """Build a minimal user ModelRequest."""
    return ModelRequest(parts=[UserPromptPart(content=text)], kind="request")


def assistant_msg(text: str) -> ModelResponse:
    """Build a minimal assistant ModelResponse."""
    return ModelResponse(parts=[TextPart(content=text)], kind="response")


def tool_call_msg(tool_call_id: str = "tc1") -> ModelResponse:
    """Build a ModelResponse containing a single tool call."""
    return ModelResponse(
        parts=[ToolCallPart(tool_name="web_search", tool_call_id=tool_call_id, args="{}")],
        kind="response",
    )


def tool_return_msg(tool_call_id: str = "tc1") -> ModelRequest:
    """Build a ModelRequest containing a single tool return."""
    return ModelRequest(
        parts=[ToolReturnPart(tool_name="web_search", tool_call_id=tool_call_id, content="result")],
        kind="request",
    )


# ── _estimate_message_tokens ─────────────────────────────────────────────────


def test_estimate_message_tokens_empty_parts():
    """Messages with no parts return 0 tokens."""
    msg = ModelRequest(parts=[], kind="request")
    assert _estimate_message_tokens(msg) == 0


def test_estimate_message_tokens_tool_call():
    """ToolCallPart with args='{}' accounts for arg tokens plus per-message overhead."""
    # args="{}" → tiktoken("{}")=1 token; overhead: 4*1+4=8 → total 9
    msg = tool_call_msg()
    assert _estimate_message_tokens(msg) == 9


def test_estimate_message_tokens_image_url_adds_constant():
    """An ImageUrl part adds the flat IMAGE_TOKEN_ESTIMATE constant."""
    msg = ModelRequest(
        parts=[UserPromptPart(content=[ImageUrl(url="https://example.com/photo.jpg")])],
        kind="request",
    )
    # overhead: 4*1 parts + 4 message = 8
    assert _estimate_message_tokens(msg) == _IMAGE_TOKEN_ESTIMATE + 8


def test_estimate_message_tokens_binary_image_adds_constant():
    """A BinaryContent image part adds the flat IMAGE_TOKEN_ESTIMATE constant."""
    msg = ModelRequest(
        parts=[UserPromptPart(content=[BinaryContent(data=b"\x89PNG", media_type="image/png")])],
        kind="request",
    )
    assert _estimate_message_tokens(msg) == _IMAGE_TOKEN_ESTIMATE + 8


# ── estimate_history_tokens ───────────────────────────────────────────────────


def test_estimate_history_tokens_empty():
    """Empty history returns 0 tokens."""
    assert estimate_history_tokens([]) == 0


def test_estimate_history_tokens_two_messages():
    """Token count for a user+assistant exchange matches the sum of individual estimates."""
    history = [user_msg("hello world"), assistant_msg("hello world")]
    assert estimate_history_tokens(history) == 24


# ── _group_into_turns ─────────────────────────────────────────────────────────


def test_group_into_turns_single_turn():
    """A single user+assistant exchange forms one turn."""
    history = [user_msg("hi"), assistant_msg("hello")]
    turns = _group_into_turns(history)
    assert len(turns) == 1
    assert turns[0] == history


def test_group_into_turns_two_turns():
    """Two user+assistant exchanges form two turns."""
    h = [user_msg("q1"), assistant_msg("a1"), user_msg("q2"), assistant_msg("a2")]
    turns = _group_into_turns(h)
    assert len(turns) == 2
    assert turns[0] == [h[0], h[1]]
    assert turns[1] == [h[2], h[3]]


def test_group_into_turns_tool_calls_stay_in_same_turn():
    """Tool call/return messages stay grouped with the user turn that triggered them."""
    h = [
        user_msg("search this"),
        tool_call_msg(),
        tool_return_msg(),
        assistant_msg("found it"),
        user_msg("thanks"),
        assistant_msg("welcome"),
    ]
    turns = _group_into_turns(h)
    assert len(turns) == 2
    assert turns[0] == h[:4]
    assert turns[1] == h[4:]


def test_group_into_turns_empty():
    """Empty history produces no turns."""
    assert not _group_into_turns([])


# ── apply_sliding_window ──────────────────────────────────────────────────────


def test_apply_sliding_window_no_trim_needed():
    """History within budget is returned unchanged with trimmed=False."""
    history = [user_msg("hi"), assistant_msg("hello")]
    result, trimmed = apply_sliding_window(history, 10_000)
    assert result == history
    assert trimmed is False


def test_apply_sliding_window_budget_zero_disables():
    """Budget of 0 disables trimming regardless of history size."""
    history = [user_msg("a" * 4000), assistant_msg("b" * 4000)]
    result, trimmed = apply_sliding_window(history, 0)
    assert result == history
    assert trimmed is False


def test_apply_sliding_window_trims_oldest_turn():
    """Oldest turn is evicted when total history exceeds budget."""
    # old_turn: user("a"*400)+assistant("b"*400) ≈ 216 tokens
    # new_turn: user("c"*400)+assistant("d"*400) ≈ 216 tokens
    # total ≈ 432 tokens; budget=250 → old_turn evicted
    old_turn = [user_msg("a" * 400), assistant_msg("b" * 400)]
    new_turn = [user_msg("c" * 400), assistant_msg("d" * 400)]
    result, trimmed = apply_sliding_window(old_turn + new_turn, 250)
    assert trimmed is True
    assert result == new_turn


def test_apply_sliding_window_keeps_last_turn_even_if_too_big():
    """A single oversized turn is kept as-is; trimmed remains False."""
    big_turn = [user_msg("a" * 4000), assistant_msg("b" * 4000)]
    result, trimmed = apply_sliding_window(big_turn, 100)
    assert result == big_turn
    assert trimmed is False


# ── resolve_conversation_budget ───────────────────────────────────────────────


@override_settings(
    DEFAULT_MAX_TOKEN_CONTEXT=8192,
    DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS=1000,
    DOCUMENT_CONTEXT_BUDGET_RATIO=0.5,
)
def test_resolve_conversation_budget_no_max_context_uses_default():
    """Models without max_token_context fall back to DEFAULT_MAX_TOKEN_CONTEXT."""

    class Cfg:  # pylint: disable=missing-class-docstring
        max_token_context = None

    # int(8192*0.5)-1000=3096
    assert resolve_conversation_budget(Cfg()) == 3096


def test_resolve_conversation_budget_zero_max_context():
    """max_token_context=0 returns 0 (trimming disabled)."""

    class Cfg:  # pylint: disable=missing-class-docstring
        max_token_context = 0

    assert resolve_conversation_budget(Cfg()) == 0


@override_settings(
    DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS=1000,
    DOCUMENT_CONTEXT_BUDGET_RATIO=0.5,
)
def test_resolve_conversation_budget_formula():
    """Budget is computed as int(max*(1-ratio))-buffer."""

    class Cfg:  # pylint: disable=missing-class-docstring
        max_token_context = 10_000

    # int(10000*0.5)-1000=4000
    assert resolve_conversation_budget(Cfg()) == 4000


@override_settings(
    DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS=0,
    DOCUMENT_CONTEXT_BUDGET_RATIO=0.0,
)
def test_resolve_conversation_budget_zero_ratio():
    """budget_ratio=0 allocates the full context window to conversation."""

    class Cfg:  # pylint: disable=missing-class-docstring
        max_token_context = 10_000

    assert resolve_conversation_budget(Cfg()) == 10_000


@override_settings(DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS=10_000)
def test_resolve_conversation_budget_logs_warning_when_buffer_exceeds_context(caplog):
    """A warning is logged when the security buffer leaves no tokens for conversation."""

    class Cfg:  # pylint: disable=missing-class-docstring
        max_token_context = 5_000

    with caplog.at_level(logging.WARNING, logger="chat.agents.history_processors"):
        result = resolve_conversation_budget(Cfg())

    assert result == 0
    assert "Sliding window disabled" in caplog.text


@override_settings(
    DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS=0,
    DOCUMENT_CONTEXT_BUDGET_RATIO=0.0,
)
def test_resolve_conversation_budget_deducts_system_prompt():
    """System prompt tokens are subtracted from the conversation budget."""
    system_prompt = "You are a helpful assistant."

    class CfgNoPrompt:  # pylint: disable=missing-class-docstring
        max_token_context = 10_000
        system_prompt = None

    class CfgWithPrompt:  # pylint: disable=missing-class-docstring
        max_token_context = 10_000
        system_prompt = "You are a helpful assistant."

    budget_without = resolve_conversation_budget(CfgNoPrompt())
    budget_with = resolve_conversation_budget(CfgWithPrompt())
    assert budget_with == budget_without - count_approx_tokens(system_prompt)


# ── _stringify_message_content ───────────────────────────────────────────────


def test_stringify_none_returns_empty():
    """None content stringifies to empty string."""
    assert _stringify_message_content(None) == ""


def test_stringify_str_returns_same():
    """String content is returned unchanged."""
    assert _stringify_message_content("hello") == "hello"


def test_stringify_list_joins():
    """List content items are joined with a space."""
    assert _stringify_message_content(["a", "b"]) == "a b"
