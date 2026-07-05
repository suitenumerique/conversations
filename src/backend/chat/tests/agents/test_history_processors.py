"""Tests for history processors."""

import pytest
from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from chat.agents import history_processors


@pytest.fixture
def _received_messages_fixture() -> list[ModelMessage]:
    """Fixture to capture messages received by the function model."""
    return []


@pytest.fixture(name="received_messages")
def received_messages_fixture_alias(
    _received_messages_fixture: list[ModelMessage],
) -> list[ModelMessage]:
    """Expose received messages fixture with a stable pytest name."""
    return _received_messages_fixture


@pytest.fixture(name="function_model")
def function_model_fixture(received_messages: list[ModelMessage]) -> FunctionModel:
    """Fixture to capture model function."""

    def capture_model_function(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        # Capture exactly what reaches the provider after history processors.
        received_messages.clear()
        received_messages.extend(messages)
        return ModelResponse(parts=[TextPart(content="Provider response")])

    return FunctionModel(capture_model_function)


def _build_turns(turn_count: int) -> list:
    """Build a list of turns for testing."""
    messages = []
    for turn in range(1, turn_count + 1):
        messages.append(ModelRequest(parts=[UserPromptPart(content=[f"user-{turn}"])]))
        messages.append(ModelResponse(parts=[TextPart(content=f"assistant-{turn}")]))
    return messages


def test_history_processors_are_applied_before_provider_call(
    function_model: FunctionModel, received_messages: list[ModelMessage]
):
    """History processors should run before provider invocation."""

    def keep_only_requests(messages: list[ModelMessage]) -> list[ModelMessage]:
        return [msg for msg in messages if isinstance(msg, ModelRequest)]

    agent = Agent(function_model, capabilities=[ProcessHistory(keep_only_requests)])
    message_history = [
        ModelRequest(parts=[UserPromptPart(content="Question 1")]),
        ModelResponse(parts=[TextPart(content="Answer 1")]),
    ]

    agent.run_sync("Question 2", message_history=message_history)
    assert len(received_messages) == 1
    assert isinstance(received_messages[0], ModelRequest)
    user_prompt_contents = [
        part.content for part in received_messages[0].parts if isinstance(part, UserPromptPart)
    ]
    assert user_prompt_contents == ["Question 1", "Question 2"]


@pytest.mark.asyncio
async def test_history_cleanup_keeps_full_history_when_under_budget():
    """No summary should be produced when the active slice fits budget."""
    messages = _build_turns(2)

    result = await history_processors.maybe_summarize_history(messages, message_token_budget=10_000)

    assert result.summary is None
    assert result.history == messages


def test_clean_tool_history_redacts_old_tool_returns_but_keeps_latest_tool_result():
    """Old tool results are compacted, latest tool result stays intact."""
    messages = [
        ModelResponse(parts=[ToolCallPart(tool_call_id="old", tool_name="search", args="{}")]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_call_id="old",
                    tool_name="search",
                    content="large old result",
                )
            ]
        ),
        ModelResponse(parts=[ToolCallPart(tool_call_id="latest", tool_name="search", args="{}")]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_call_id="latest",
                    tool_name="search",
                    content="fresh result",
                )
            ]
        ),
    ]

    result = history_processors.clean_tool_history(messages)

    old_return = result[1].parts[0]
    latest_return = result[3].parts[0]
    assert isinstance(old_return, ToolReturnPart)
    assert isinstance(latest_return, ToolReturnPart)
    assert old_return.content == "<search response compacted>"
    assert latest_return.content == "fresh result"


@pytest.mark.asyncio
async def test_history_cleanup_over_budget_generates_summary_and_advances_checkpoint(monkeypatch):
    """Summary is generated when unsummarized runtime history exceeds budget."""
    summarized_messages = []

    async def fake_summary(messages, *, max_tokens=300, previous_summary=None):
        summarized_messages.extend(messages)
        _ = max_tokens
        _ = previous_summary
        return "summary-v1"

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(3)

    result = await history_processors.maybe_summarize_history(
        messages, message_token_budget=1, context_messages=1
    )

    assert result.summary == "summary-v1"
    assert result.summary_checkpoint == len(messages)
    assert result.history == messages[5:]
    assert summarized_messages == messages[: result.summary_checkpoint]


@pytest.mark.asyncio
async def test_history_cleanup_existing_summary_uses_checkpoint_slice(monkeypatch):
    """When already summarized, runtime history starts at checkpoint minus context."""

    async def fake_summary(_messages, *, max_tokens=300, previous_summary=None):
        _ = max_tokens
        _ = previous_summary
        raise AssertionError("Summary should not be regenerated at turn 5")

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(5)

    result = await history_processors.maybe_summarize_history(
        messages,
        summary_checkpoint=6,
        message_token_budget=10_000,
        context_messages=1,
    )

    assert result.summary is None
    assert result.history == messages[5:]


@pytest.mark.asyncio
async def test_history_cleanup_budget_only_counts_active_window_after_checkpoint(monkeypatch):
    """Old summarized messages should not retrigger summaries after checkpoint."""

    async def fake_summary(_messages, *, max_tokens=300, previous_summary=None):
        _ = max_tokens
        _ = previous_summary
        raise AssertionError("Messages before the active window should not count")

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = [
        ModelRequest(parts=[UserPromptPart(content=["old user " + ("x " * 500)])]),
        ModelResponse(parts=[TextPart(content="old assistant " + ("x " * 500))]),
        ModelRequest(parts=[UserPromptPart(content=["context user"])]),
        ModelResponse(parts=[TextPart(content="context assistant")]),
        ModelRequest(parts=[UserPromptPart(content=["new user"])]),
        ModelResponse(parts=[TextPart(content="new assistant")]),
    ]

    result = await history_processors.maybe_summarize_history(
        messages,
        summary_checkpoint=4,
        message_token_budget=100,
        context_messages=1,
    )

    assert result.summary is None
    assert result.history == messages[3:]


@pytest.mark.asyncio
async def test_history_cleanup_does_not_resummarize_when_checkpoint_is_current(monkeypatch):
    """After a summary, context overlap alone should not be summarized again."""

    async def fake_summary(_messages, *, max_tokens=300, previous_summary=None):
        _ = max_tokens
        _ = previous_summary
        raise AssertionError("Latest active turn should not be summarized")

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(3)

    result = await history_processors.maybe_summarize_history(
        messages,
        summary_checkpoint=len(messages),
        message_token_budget=1,
        context_messages=1,
    )

    assert result.summary is None
    assert result.summary_checkpoint is None
    assert result.history == messages[5:]


@pytest.mark.asyncio
async def test_history_cleanup_never_returns_empty_history_when_checkpoint_is_at_end():
    """pydantic-ai rejects empty processed history when it passed history in."""
    messages = _build_turns(2)

    result = await history_processors.maybe_summarize_history(
        messages,
        summary_checkpoint=len(messages),
        message_token_budget=10_000,
        context_messages=1,
    )

    assert result.summary is None
    assert result.history == messages[3:]


def test_clean_tool_history_has_no_summary_checkpoint_behavior():
    """The pydantic-ai history processor path only cleans tools."""
    messages = _build_turns(2)

    result = history_processors.clean_tool_history(messages)

    assert result == messages


@pytest.mark.asyncio
async def test_history_cleanup_summary_failure_keeps_runtime_slice(monkeypatch):
    """If summary generation fails, keep runtime slice unchanged."""

    async def fake_summary(_messages, *, max_tokens=300, previous_summary=None):
        _ = max_tokens
        _ = previous_summary

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(4)

    result = await history_processors.maybe_summarize_history(
        messages,
        summary_checkpoint=2,
        message_token_budget=1,
        context_messages=1,
    )

    assert result.summary is None
    assert result.history == messages[1:]


def test_should_generate_conversation_summary_when_budget_exceeded():
    """Frontend summary event should trigger only when over budget."""
    messages = _build_turns(3)
    assert history_processors.should_generate_conversation_summary(messages, message_token_budget=1)
    assert not history_processors.should_generate_conversation_summary(
        messages, message_token_budget=10_000
    )
    assert not history_processors.should_generate_conversation_summary(
        messages,
        summary_checkpoint=len(messages),
        message_token_budget=1,
        context_messages=1,
    )
    assert not history_processors.should_generate_conversation_summary(
        messages,
        summary_checkpoint=28,
        message_token_budget=1,
        context_messages=1,
    )
    messages_with_large_summarized_prefix = [
        ModelRequest(parts=[UserPromptPart(content=["old user " + ("x " * 500)])]),
        ModelResponse(parts=[TextPart(content="old assistant " + ("x " * 500))]),
        ModelRequest(parts=[UserPromptPart(content=["context user"])]),
        ModelResponse(parts=[TextPart(content="context assistant")]),
        ModelRequest(parts=[UserPromptPart(content=["new user"])]),
        ModelResponse(parts=[TextPart(content="new assistant")]),
    ]
    assert not history_processors.should_generate_conversation_summary(
        messages_with_large_summarized_prefix,
        summary_checkpoint=4,
        message_token_budget=100,
        context_messages=1,
    )


def test_safe_clean_tool_history_falls_back_to_raw_history(monkeypatch):
    """Unexpected cleanup errors should not break the conversation flow."""
    messages = _build_turns(2)

    def raise_cleanup(_messages):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(history_processors, "clean_tool_history", raise_cleanup)

    result = history_processors.safe_clean_tool_history(messages)

    assert result == messages


@pytest.mark.asyncio
async def test_maybe_summarize_history_falls_back_on_unexpected_error(monkeypatch):
    """Unexpected summarization errors should keep the active history slice."""
    messages = _build_turns(4)

    def raise_estimate(_message):
        raise RuntimeError("token estimate failed")

    monkeypatch.setattr(history_processors, "_estimate_message_tokens", raise_estimate)

    result = await history_processors.maybe_summarize_history(
        messages,
        summary_checkpoint=2,
        message_token_budget=1,
        context_messages=1,
    )

    assert result.summary is None
    assert result.history == messages[1:]
