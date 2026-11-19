"""Tests for the token counting and budget utilities."""

from unittest import mock

from chat.tokens import count_approx_tokens, truncate_to_tokens


def test_truncate_to_tokens_keeps_text_within_the_limit():
    """Text over the limit is cut to at most that many tokens, from the start."""
    text = "Le réseau compte quatorze médiathèques. " * 50

    truncated = truncate_to_tokens(text, 20)

    assert count_approx_tokens(truncated) <= 20
    assert text.startswith(truncated)


def test_truncate_to_tokens_leaves_short_text_untouched():
    """Text already within the limit is returned as is."""
    assert truncate_to_tokens("Trois axes prioritaires.", 100) == "Trois axes prioritaires."


def test_truncate_to_tokens_falls_back_to_a_heuristic():
    """When tiktoken is unavailable, the cut follows the 3-characters heuristic."""
    with mock.patch("chat.tokens._get_token_encoding", side_effect=RuntimeError("boom")):
        truncated = truncate_to_tokens("abcdefghij" * 10, 5)

    assert truncated == "abcdefghijabcde"
