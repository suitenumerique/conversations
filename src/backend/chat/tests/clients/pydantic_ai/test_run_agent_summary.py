"""Tests for _run_agent summary-event wiring and history-summary persistence."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from chat.agents.history_processors import HistoryCleanupResult
from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import AIAgentService, DocumentParsingResult
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def _llm_config(settings):
    """Provide a valid model configuration so AIAgentService can be constructed."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            max_token_context=4000,
            provider=LLMProvider(
                hrid="unused",
                base_url="https://example.com",
                api_key="key",
            ),
        ),
    }


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """A single user message, enough to drive _run_agent."""
    return [UIMessage(id="msg-1", role="user", content="Hello", parts=[])]


@pytest.mark.asyncio
async def test_apply_history_cleanup_persists_summary_metadata():
    """_apply_history_cleanup copies the generated summary + checkpoint onto the conversation.

    Guards the seam between the pure summarization functions and the conversation
    model: a generated summary must land on both the in-memory cache and the
    conversation instance that _run_agent later saves.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    cleanup = HistoryCleanupResult(history=[], summary="A generated summary", summary_checkpoint=4)
    with patch(
        "chat.clients.pydantic_ai.maybe_summarize_history",
        AsyncMock(return_value=cleanup),
    ):
        result = await service._apply_history_cleanup([], allow_summary_generation=True)

    assert result == []
    assert service._history_summary == "A generated summary"
    assert service._history_summary_checkpoint == 4
    assert service.conversation.history_summary == "A generated summary"
    assert service.conversation.history_summary_checkpoint == 4


@pytest.mark.asyncio
async def test_apply_history_cleanup_leaves_metadata_untouched_without_summary():
    """When no summary is generated, existing summary metadata is not clobbered."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    service._history_summary = "existing"
    service._history_summary_checkpoint = 2

    cleanup = HistoryCleanupResult(history=[])
    with patch(
        "chat.clients.pydantic_ai.maybe_summarize_history",
        AsyncMock(return_value=cleanup),
    ):
        await service._apply_history_cleanup([], allow_summary_generation=False)

    assert service._history_summary == "existing"
    assert service._history_summary_checkpoint == 2


class _FakeRun:
    """Minimal stand-in for a pydantic-ai agent run result."""

    def __init__(self):
        self.result = MagicMock()
        self.result.new_messages.return_value = []
        self.result.output = ""
        self.usage = MagicMock(input_tokens=0, output_tokens=0)


async def _empty_async_gen(*_args, **_kwargs):
    """An async generator that yields nothing."""
    if False:  # pragma: no cover - never yields, only makes this a generator
        yield


@pytest.mark.asyncio
async def test_run_agent_emits_summary_events_when_summarization_triggers(ui_messages):
    """Regression test: _run_agent must define should_emit_summary_event, tool_call_id
    and conversation_has_own_documents.

    A dropped block during history rewriting previously left these undefined, crashing
    every agent run with UnboundLocalError/NameError. All existing tests mock _run_agent
    itself, so nothing exercised the real method. This drives the real _run_agent with the
    summarization path enabled and asserts the running/done event pair brackets the run.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def fake_prepare(_messages):
        usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
        return ("prompt", [], [], [], usage, [], False)

    async def fake_handle_docs(*_args, **_kwargs):
        yield DocumentParsingResult(success=True, has_documents=False)

    @asynccontextmanager
    async def fake_iter(*_args, **_kwargs):
        yield _FakeRun()

    service.conversation_agent = MagicMock()
    service.conversation_agent.iter = fake_iter

    with (
        patch.object(service, "_prepare_agent_run", side_effect=fake_prepare),
        patch.object(service, "_handle_input_documents", side_effect=fake_handle_docs),
        patch.object(service, "_apply_history_cleanup", AsyncMock(return_value=[])),
        patch.object(service, "_agent_stop_streaming", AsyncMock()),
        patch.object(service, "_setup_self_documentation_tool"),
        patch.object(service, "_setup_web_search_tool"),
        patch.object(service, "_setup_web_search"),
        patch.object(service, "_check_should_enable_rag", AsyncMock(return_value=False)),
        patch.object(service, "_process_agent_nodes", side_effect=_empty_async_gen),
        patch.object(service, "_finalize_conversation", side_effect=_empty_async_gen),
        patch("chat.clients.pydantic_ai.should_generate_conversation_summary", return_value=True),
        patch("chat.clients.pydantic_ai.get_mcp_servers", return_value=[]),
        patch("chat.clients.pydantic_ai._extract_co2_from_usage", return_value=0),
    ):
        events = [event async for event in service._run_agent(ui_messages)]

    tool_calls = [e for e in events if isinstance(e, events_v4.ToolCallPart)]
    tool_results = [e for e in events if isinstance(e, events_v4.ToolResultPart)]

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "summarize"
    assert tool_calls[0].args["state"] == "running"

    assert len(tool_results) == 1
    assert tool_results[0].result == {"state": "done"}
    assert tool_results[0].tool_call_id == tool_calls[0].tool_call_id


@pytest.mark.asyncio
async def test_run_agent_skips_summary_events_when_summarization_not_triggered(ui_messages):
    """No summary events are emitted when summarization is not needed (and still no crash)."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def fake_prepare(_messages):
        usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
        return ("prompt", [], [], [], usage, [], False)

    async def fake_handle_docs(*_args, **_kwargs):
        yield DocumentParsingResult(success=True, has_documents=False)

    @asynccontextmanager
    async def fake_iter(*_args, **_kwargs):
        yield _FakeRun()

    service.conversation_agent = MagicMock()
    service.conversation_agent.iter = fake_iter

    with (
        patch.object(service, "_prepare_agent_run", side_effect=fake_prepare),
        patch.object(service, "_handle_input_documents", side_effect=fake_handle_docs),
        patch.object(service, "_apply_history_cleanup", AsyncMock(return_value=[])),
        patch.object(service, "_agent_stop_streaming", AsyncMock()),
        patch.object(service, "_setup_self_documentation_tool"),
        patch.object(service, "_setup_web_search_tool"),
        patch.object(service, "_setup_web_search"),
        patch.object(service, "_check_should_enable_rag", AsyncMock(return_value=False)),
        patch.object(service, "_process_agent_nodes", side_effect=_empty_async_gen),
        patch.object(service, "_finalize_conversation", side_effect=_empty_async_gen),
        patch("chat.clients.pydantic_ai.should_generate_conversation_summary", return_value=False),
        patch("chat.clients.pydantic_ai.get_mcp_servers", return_value=[]),
        patch("chat.clients.pydantic_ai._extract_co2_from_usage", return_value=0),
    ):
        events = [event async for event in service._run_agent(ui_messages)]

    assert not [e for e in events if isinstance(e, events_v4.ToolCallPart)]
    assert not [e for e in events if isinstance(e, events_v4.ToolResultPart)]
