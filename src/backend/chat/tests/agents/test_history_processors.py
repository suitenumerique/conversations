"""Tests for history processors."""

import pytest
from pydantic_ai import Agent, ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
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

    agent = Agent(function_model, history_processors=[keep_only_requests])
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
async def test_history_cleanup_keeps_full_history_before_turn_3():
    """No summary should be produced before summary interval."""
    messages = _build_turns(2)

    result = await history_processors.history_cleanup(messages)

    assert result.summary is None
    assert result.history == messages


@pytest.mark.asyncio
async def test_history_cleanup_turn_3_generates_summary_and_keeps_last_two_turns(monkeypatch):
    """A summary is generated at interval boundary and context is trimmed."""

    async def fake_summary(_messages, *, _max_tokens=300, _previous_summary=None):
        return "summary-v1"

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(3)

    result = await history_processors.history_cleanup(messages)

    assert result.summary == "summary-v1"
    assert len(result.history) == 4
    assert result.history == messages[-4:]


@pytest.mark.asyncio
async def test_history_cleanup_turn_5_keeps_summary_and_last_two_turns(monkeypatch):
    """Existing summary is reused between summary boundaries."""

    async def fake_summary(_messages, *, _max_tokens=300, _previous_summary=None):
        raise AssertionError("Summary should not be regenerated at turn 5")

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(5)

    result = await history_processors.history_cleanup(messages, previous_summary="summary-v1")

    assert result.summary is None
    assert len(result.history) == 4
    assert result.history == messages[-4:]


@pytest.mark.asyncio
async def test_history_cleanup_turn_4_keeps_summary_and_last_two_turns(monkeypatch):
    """Context remains capped when a summary already exists."""

    async def fake_summary(_messages, *, _max_tokens=300, _previous_summary=None):
        raise AssertionError("Summary should not be regenerated at turn 4")

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(4)

    result = await history_processors.history_cleanup(messages, previous_summary="summary-v1")

    assert result.summary is None
    assert len(result.history) == 4
    assert result.history == messages[-4:]


@pytest.mark.asyncio
async def test_history_cleanup_turn_6_updates_summary_and_keeps_last_two_turns(monkeypatch):
    """Summary should be refreshed at the next boundary."""

    async def fake_summary(summary_messages, *, max_tokens=300, previous_summary=None):
        _ = max_tokens
        assert previous_summary == "summary-v1"
        assert len(summary_messages) == 6
        assert summary_messages == messages[-6:]
        return "summary-v2"

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(6)

    result = await history_processors.history_cleanup(messages, previous_summary="summary-v1")

    assert result.summary == "summary-v2"
    assert len(result.history) == 4
    assert result.history == messages[-4:]


@pytest.mark.asyncio
async def test_history_cleanup_turn_8_keeps_summary_and_last_two_turns(monkeypatch):
    """Summary should not regenerate on non-boundary turns."""

    async def fake_summary(_messages, *, _max_tokens=300, _previous_summary=None):
        raise AssertionError("Summary should not be regenerated at turn 8")

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(8)

    result = await history_processors.history_cleanup(messages, previous_summary="summary-v2")

    assert result.summary is None
    assert len(result.history) == 4
    assert result.history == messages[-4:]


@pytest.mark.asyncio
async def test_history_cleanup_turn_9_regenerates_summary(monkeypatch):
    """Summary should regenerate at the following boundary turn."""

    async def fake_summary(_messages, *, _max_tokens=300, previous_summary=None):
        assert previous_summary == "summary-v2"
        return "summary-v3"

    monkeypatch.setattr(history_processors, "conversation_summarization", fake_summary)
    messages = _build_turns(9)

    result = await history_processors.history_cleanup(messages, previous_summary="summary-v2")

    assert result.summary == "summary-v3"
    assert len(result.history) == 4
    assert result.history == messages[-4:]
