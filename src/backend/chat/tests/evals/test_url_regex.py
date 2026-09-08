"""Tests for the URL-hallucination regex evaluator."""

from types import SimpleNamespace

from chat.evals.evaluators.url_regex import UrlRegexEvaluator


def _ctx(output, *, user_message="", tool_output=None, attributes=None):
    """Build a minimal EvaluatorContext-like stub with the attributes the evaluator reads."""
    return SimpleNamespace(
        output=output,
        inputs=SimpleNamespace(user_message=user_message, tool_output=tool_output),
        attributes=attributes or {},
    )


def test_non_string_output_does_not_raise():
    """A non-str ctx.output is treated as containing no URLs (no TypeError)."""
    result = UrlRegexEvaluator().evaluate(_ctx(output={"unexpected": "dict"}))
    assert result.value is True


def test_hallucinated_url_is_flagged():
    """A URL in the output that isn't in any allowed source fails the case."""
    result = UrlRegexEvaluator().evaluate(
        _ctx(output="See https://evil.example/x", user_message="hi")
    )
    assert result.value is False
    assert "evil.example" in result.reason


def test_url_present_in_user_message_is_allowed():
    """A URL echoed from the user message is not flagged as hallucinated."""
    result = UrlRegexEvaluator().evaluate(
        _ctx(output="Go to https://ok.example/a", user_message="https://ok.example/a")
    )
    assert result.value is True
