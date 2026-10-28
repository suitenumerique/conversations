"""Tests for chat tool utilities."""

import inspect
import logging
from typing import get_type_hints

import pytest
from pydantic_ai import ModelRetry, RunContext

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import (
    extract_domain,
    filter_blocked_results,
    is_blocked_url,
    last_model_retry_soft_fail,
    normalize_domain,
    parse_domain_list,
)


def test_normalize_domain():
    """Domain normalization is case-insensitive and strips www. and dots."""
    assert normalize_domain("Facebook.COM") == "facebook.com"
    assert normalize_domain("  www.tiktok.com. ") == "tiktok.com"
    assert normalize_domain("") == ""


def test_extract_domain():
    """Hostname extraction handles subdomains, ports and garbage input."""
    assert extract_domain("https://m.facebook.com/some/page") == "m.facebook.com"
    assert extract_domain("https://WWW.X.COM:443/u") == "x.com"
    assert extract_domain("not a url") == ""
    assert extract_domain("") == ""


def test_is_blocked_url_matches_domain_and_subdomains():
    """Blocked domains match exactly and on subdomains, case-insensitively."""
    blocked = {"facebook.com", "x.com"}

    assert is_blocked_url("https://facebook.com/some/page", blocked) is True
    assert is_blocked_url("https://www.facebook.com/page", blocked) is True
    assert is_blocked_url("https://m.facebook.com/page", blocked) is True
    assert is_blocked_url("https://X.com/user/status", blocked) is True
    assert is_blocked_url("https://example.com/page", blocked) is False
    # Similar suffixes must not match.
    assert is_blocked_url("https://notfacebook.com/page", blocked) is False
    assert is_blocked_url("https://facebook.com.evil.com/page", blocked) is False
    assert is_blocked_url("not a url", blocked) is False
    assert is_blocked_url("https://facebook.com/page", set()) is False
    # Blocklist entries are normalized too.
    assert is_blocked_url("https://facebook.com/page", {"  WWW.Facebook.COM. "}) is True


def test_parse_domain_list():
    """Blocklist settings parse from comma strings, iterables, or falsy values."""
    assert parse_domain_list("facebook.com, x.com ") == {"facebook.com", "x.com"}
    assert parse_domain_list(["Facebook.com", "", "x.com"]) == {"facebook.com", "x.com"}
    assert parse_domain_list("") == set()
    assert parse_domain_list(None) == set()


def test_filter_blocked_results_drops_and_caps(caplog):
    """Shared filter drops blocklisted URLs, keeps order, and honors the cap."""
    raw = [
        {"url": "https://facebook.com/a", "title": "A"},
        {"url": "https://example.com/kept", "title": "Kept"},
        {"url": "https://www.tiktok.com/b", "title": "B"},
        {"url": "https://example.com/kept2", "title": "Kept2"},
    ]

    with caplog.at_level(logging.INFO):
        kept = filter_blocked_results(raw, {"facebook.com", "tiktok.com"}, max_results=2)

    assert [r["url"] for r in kept] == ["https://example.com/kept", "https://example.com/kept2"]
    assert "Filtered 2 blocked web search result(s)" in caplog.text


def test_filter_blocked_results_without_cap_or_blocklist():
    """No cap keeps every survivor; no blocklist keeps everything."""
    raw = [{"url": "https://example.com/a"}, {"url": "https://example.com/b"}]

    assert filter_blocked_results(raw, {"facebook.com"}) == raw
    assert filter_blocked_results(raw, set()) == raw


def test_last_model_retry_soft_fail_preserves_function_metadata():
    """Test that the decorator preserves function metadata for schema generation."""

    @last_model_retry_soft_fail
    async def example_tool(ctx: RunContext, query: str, limit: int = 10) -> str:  # pylint: disable=unused-argument
        """
        Example tool function.

        Args:
            ctx: The run context.
            query: The search query.
            limit: Maximum number of results.

        Returns:
            The search results.
        """
        return f"Results for {query} (limit: {limit})"

    # Check that function name is preserved
    assert example_tool.__name__ == "example_tool"

    # Check that docstring is preserved
    assert example_tool.__doc__ is not None
    assert "Example tool function" in example_tool.__doc__

    # Check that signature is preserved
    sig = inspect.signature(example_tool)
    assert "ctx" in sig.parameters
    assert "query" in sig.parameters
    assert "limit" in sig.parameters
    assert sig.parameters["limit"].default == 10

    # Check that type hints are preserved
    type_hints = get_type_hints(example_tool)
    assert "query" in type_hints
    assert type_hints["query"] == str
    assert "limit" in type_hints
    assert type_hints["limit"] == int
    assert type_hints["return"] == str


@pytest.mark.asyncio
async def test_last_model_retry_soft_fail_normal_execution():
    """Test that the decorator doesn't interfere with normal execution."""

    @last_model_retry_soft_fail
    async def example_tool(_ctx: RunContext, value: str) -> str:
        """Example tool."""
        return f"Result: {value}"

    # Create a mock context
    class MockContext:
        """Fake context for testing."""

        max_retries = 3
        retries = {}
        tool_name = "example_tool"

    ctx = MockContext()
    result = await example_tool(ctx, "test")
    assert result == "Result: test"


@pytest.mark.asyncio
async def test_last_model_retry_soft_fail_handles_retry_exception():
    """Test that the decorator handles ModelRetry exceptions correctly."""

    @last_model_retry_soft_fail
    async def failing_tool(_ctx: RunContext, should_fail: bool) -> str:
        """Tool that can raise ModelRetry."""
        if should_fail:
            raise ModelRetry("Please retry with different parameters")
        return "Success"

    # Create a mock context
    class MockContext:
        """Fake context for testing."""

        max_retries = 3
        retries = {}
        tool_name = "failing_tool"

    ctx = MockContext()

    # Test when retries haven't been exhausted - should re-raise
    with pytest.raises(ModelRetry):
        await failing_tool(ctx, should_fail=True)


@pytest.mark.asyncio
async def test_last_model_retry_soft_fail_returns_message_when_max_retries_reached():
    """Test that the decorator returns the error message when max retries is reached."""

    @last_model_retry_soft_fail
    async def failing_tool(_ctx: RunContext, should_fail: bool) -> str:
        """Tool that can raise ModelRetry."""
        if should_fail:
            raise ModelRetry("Please retry with different parameters.")
        return "Success"

    # Create a mock context with max retries already reached
    class MockContext:
        """Fake context for testing."""

        max_retries = 3
        retries = {"failing_tool": 3}
        tool_name = "failing_tool"

    ctx = MockContext()

    # Test when retries have been exhausted - should return message
    result = await failing_tool(ctx, should_fail=True)
    assert result == (
        "Please retry with different parameters. "
        "You must explain this to the user and not try to answer based on your knowledge."
    )


@pytest.mark.asyncio
async def test_last_model_retry_soft_fail_returns_message_when_model_cannot_retry():
    """Test that the decorator returns the error message when ModelCannotRetry is raised."""

    @last_model_retry_soft_fail
    async def failing_tool(_ctx: RunContext, should_fail: bool) -> str:
        """Tool that can raise ModelRetry."""
        if should_fail:
            raise ModelCannotRetry("This is broken duh.")
        return "Success"

    # Create a mock context with max retries already reached
    class MockContext:
        """Fake context for testing."""

        max_retries = 3
        retries = {"failing_tool": 3}
        tool_name = "failing_tool"

    ctx = MockContext()

    # Test when retries have been exhausted - should return message
    result = await failing_tool(ctx, should_fail=True)
    assert result == "This is broken duh."


@pytest.mark.asyncio
async def test_last_model_retry_soft_fail_does_not_log_run_context(caplog):
    """The run context carries the user prompt and history: only the tool name is logged."""

    @last_model_retry_soft_fail
    async def failing_tool(_ctx: RunContext) -> str:
        """Tool that raises ModelRetry."""
        raise ModelRetry("Please retry.")

    class MockContext:
        """Fake context whose repr exposes the prompt, like RunContext does."""

        max_retries = 3
        retries = {}
        tool_name = "failing_tool"

        def __repr__(self):
            return "RunContext(prompt='My secret prompt')"

    with caplog.at_level(logging.ERROR), pytest.raises(ModelRetry):
        await failing_tool(MockContext())

    assert "Tool 'failing_tool' raised ModelRetry: Please retry." in caplog.text
    assert "My secret prompt" not in caplog.text
