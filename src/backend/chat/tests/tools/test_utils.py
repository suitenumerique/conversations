"""Tests for chat tool utilities."""

import inspect
from typing import get_type_hints

import pytest
from pydantic_ai import ModelRetry, RunContext

from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail


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
