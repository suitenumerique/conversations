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


def test_build_active_history_keeps_full_history_within_context_window():
    """The whole history is kept when it fits inside the context window."""
    messages = _build_turns(2)

    result = history_processors.build_active_history(
        messages, summary_checkpoint=0, context_messages=10
    )

    assert result == messages


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
async def test_generate_history_summary_returns_summary_and_advances_checkpoint(monkeypatch):
    """Generation summarizes everything after the checkpoint and advances it to the end."""
    summarized_messages = []

    async def fake_summary(messages, *, max_tokens=300, previous_summary=None):
        summarized_messages.extend(messages)
        _ = max_tokens
        _ = previous_summary
        return "summary-v1"

    monkeypatch.setattr(history_processors, "summarize_conversation", fake_summary)
    messages = _build_turns(3)

    summary, checkpoint = await history_processors.generate_history_summary(messages)

    assert summary == "summary-v1"
    assert checkpoint == len(messages)
    assert summarized_messages == messages


@pytest.mark.asyncio
async def test_generate_history_summary_summarizes_only_after_checkpoint(monkeypatch):
    """With an existing checkpoint, only messages after it are sent to the model."""
    summarized_messages = []

    async def fake_summary(messages, *, max_tokens=300, previous_summary=None):
        summarized_messages.extend(messages)
        _ = max_tokens
        _ = previous_summary
        return "summary-v2"

    monkeypatch.setattr(history_processors, "summarize_conversation", fake_summary)
    messages = _build_turns(5)

    summary, checkpoint = await history_processors.generate_history_summary(
        messages, summary_checkpoint=6
    )

    assert summary == "summary-v2"
    assert checkpoint == len(messages)
    assert summarized_messages == messages[6:]


def test_build_active_history_starts_at_checkpoint_minus_context():
    """The runtime window starts `context_messages` before the checkpoint."""
    messages = _build_turns(5)

    result = history_processors.build_active_history(
        messages, summary_checkpoint=6, context_messages=1
    )

    assert result == messages[5:]


def test_build_active_history_drops_the_summarized_prefix():
    """A large already-summarized prefix is dropped from the runtime window."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content=["old user " + ("x " * 500)])]),
        ModelResponse(parts=[TextPart(content="old assistant " + ("x " * 500))]),
        ModelRequest(parts=[UserPromptPart(content=["context user"])]),
        ModelResponse(parts=[TextPart(content="context assistant")]),
        ModelRequest(parts=[UserPromptPart(content=["new user"])]),
        ModelResponse(parts=[TextPart(content="new assistant")]),
    ]

    result = history_processors.build_active_history(
        messages, summary_checkpoint=4, context_messages=1
    )

    assert result == messages[3:]


def test_build_active_history_never_empty_when_checkpoint_at_end():
    """pydantic-ai rejects empty processed history, so the last message is kept."""
    messages = _build_turns(2)

    result = history_processors.build_active_history(
        messages, summary_checkpoint=len(messages), context_messages=1
    )

    assert result == messages[3:]


def test_clean_tool_history_has_no_summary_checkpoint_behavior():
    """The pydantic-ai history processor path only cleans tools."""
    messages = _build_turns(2)

    result = history_processors.clean_tool_history(messages)

    assert result == messages


@pytest.mark.asyncio
async def test_generate_history_summary_raises_when_model_returns_nothing(monkeypatch):
    """No degraded turn: an empty summary raises so the task retries."""

    async def fake_summary(_messages, *, max_tokens=300, previous_summary=None):
        _ = max_tokens, previous_summary

    monkeypatch.setattr(history_processors, "summarize_conversation", fake_summary)
    messages = _build_turns(20)

    with pytest.raises(history_processors.SummarizationRequiredError):
        await history_processors.generate_history_summary(messages)


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
