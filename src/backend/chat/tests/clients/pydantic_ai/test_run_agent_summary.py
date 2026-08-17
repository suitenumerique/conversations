"""Tests for _run_agent summary-event wiring and history-summary persistence."""
# pylint: disable=protected-access  # tests intentionally access private members
# pylint: disable=using-constant-test,unreachable  # if False: generator stubs

from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from django.utils import timezone

import pytest
from asgiref.sync import sync_to_async

from chat.agents.history_processors import SummarizationRequiredError
from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import AIAgentService, DocumentParsingResult
from chat.constants import (
    HISTORY_SUMMARY_CLAIM_DEAD_GRACE_SECONDS,
    HISTORY_SUMMARY_POLL_INTERVAL_SECONDS,
)
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
async def test_build_model_history_trims_without_generating_or_claiming():
    """The turn only trims history: no LLM, no summary write, no claim taken."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    service._history_summary_checkpoint = 3

    history = ["m0", "m1", "m2", "m3", "m4"]
    with patch(
        "chat.clients.pydantic_ai.build_active_history",
        return_value=history[2:],
    ) as trim:
        result = service._build_model_history(history)

    assert result == history[2:]
    trim.assert_called_once()
    # No summary generated, nothing persisted, no claim taken.
    assert service._history_summary is None
    await service.conversation.arefresh_from_db()
    assert service.conversation.history_summary_claimed_at is None
    assert service.conversation.history_summary == ""


class _FakeRun:
    """Minimal stand-in for a pydantic-ai agent run result."""

    def __init__(self):
        """Build a fake run exposing empty results and zero usage."""
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
        """Return a stub agent-run preparation tuple."""
        usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
        return ("prompt", [], [], [], usage, [], False)

    async def fake_handle_docs(*_args, **_kwargs):
        """Yield a stub document-parsing result with no documents."""
        yield DocumentParsingResult(success=True, has_documents=False)

    @asynccontextmanager
    async def fake_iter(*_args, **_kwargs):
        """Yield a fake agent run as an async context manager."""
        yield _FakeRun()

    service.conversation_agent = MagicMock()
    service.conversation_agent.iter = fake_iter

    with (
        patch.object(service, "_prepare_agent_run", side_effect=fake_prepare),
        patch.object(service, "_handle_input_documents", side_effect=fake_handle_docs),
        patch.object(service, "_build_model_history", return_value=[]),
        patch.object(service, "_agent_stop_streaming", AsyncMock()),
        patch.object(service, "_setup_self_documentation_tool"),
        patch.object(service, "_setup_web_search_tool"),
        patch.object(service, "_setup_web_search"),
        patch.object(service, "_check_should_enable_rag", AsyncMock(return_value=False)),
        patch.object(service, "_process_agent_nodes", side_effect=_empty_async_gen),
        patch.object(service, "_finalize_conversation", side_effect=_empty_async_gen),
        # True at start (phase triggers), False on the re-check (summary landed).
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            side_effect=[True, False],
        ),
        patch("chat.clients.pydantic_ai.get_mcp_servers", return_value=[]),
        patch("chat.clients.pydantic_ai._extract_co2_from_usage", return_value=0),
        patch.object(service, "_wait_for_history_summary", side_effect=_empty_async_gen),
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
async def test_stream_content_emits_summarization_failed_error(ui_messages):
    """SummarizationRequiredError becomes an ErrorPart and persists the user message."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def failing_run_agent(_messages, _force_web_search=False):
        """Fake agent run that raises SummarizationRequiredError."""
        raise SummarizationRequiredError("model down")
        yield  # pragma: no cover - makes this an async generator

    with (
        patch.object(service, "_run_agent", side_effect=failing_run_agent),
        patch.object(service, "_persist_user_message_on_error", AsyncMock()) as persist,
    ):
        chunks = [chunk async for chunk in service.stream_data_async(ui_messages)]

    assert any("summarization_failed" in chunk for chunk in chunks)
    persist.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_agent_skips_summary_events_when_summarization_not_triggered(ui_messages):
    """No summary events are emitted when summarization is not needed (and still no crash)."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def fake_prepare(_messages):
        """Return a stub agent-run preparation tuple."""
        usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
        return ("prompt", [], [], [], usage, [], False)

    async def fake_handle_docs(*_args, **_kwargs):
        """Yield a stub document-parsing result with no documents."""
        yield DocumentParsingResult(success=True, has_documents=False)

    @asynccontextmanager
    async def fake_iter(*_args, **_kwargs):
        """Yield a fake agent run as an async context manager."""
        yield _FakeRun()

    service.conversation_agent = MagicMock()
    service.conversation_agent.iter = fake_iter

    with (
        patch.object(service, "_prepare_agent_run", side_effect=fake_prepare),
        patch.object(service, "_handle_input_documents", side_effect=fake_handle_docs),
        patch.object(service, "_build_model_history", return_value=[]),
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
        patch.object(service, "_wait_for_history_summary", side_effect=_empty_async_gen),
    ):
        events = [event async for event in service._run_agent(ui_messages)]

    assert not [e for e in events if isinstance(e, events_v4.ToolCallPart)]
    assert not [e for e in events if isinstance(e, events_v4.ToolResultPart)]


@pytest.mark.asyncio
async def test_wait_for_history_summary_returns_when_checkpoint_advances():
    """The wait ends as soon as another worker's summary lands."""
    conversation = await sync_to_async(ChatConversationFactory)(
        history_summary_claimed_at=timezone.now(),
    )
    service = AIAgentService(conversation, user=conversation.owner)
    ticks = 0

    async def fake_sleep(_seconds):
        """Patched sleep that lands the summary on the second poll tick."""
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            # Simulate the task completing on another worker.
            await sync_to_async(type(conversation).objects.filter(pk=conversation.pk).update)(
                history_summary="done elsewhere", history_summary_checkpoint=8
            )

    with patch("chat.clients.pydantic_ai.asyncio.sleep", side_effect=fake_sleep):
        events = [event async for event in service._wait_for_history_summary()]

    assert ticks >= 2
    assert all(e.data == [{"type": "keep_alive"}] for e in events)
    assert service.conversation.history_summary_checkpoint == 8


@pytest.mark.asyncio
async def test_wait_for_history_summary_returns_after_grace_on_dead_claim():
    """A claim past the TTL belongs to a dead worker: give up once the grace elapses."""
    conversation = await sync_to_async(ChatConversationFactory)(
        history_summary_claimed_at=timezone.now() - timedelta(seconds=181),
    )
    service = AIAgentService(conversation, user=conversation.owner)
    fake_now = 0.0

    async def fake_sleep(seconds):
        """Patched sleep that advances the fake monotonic clock."""
        nonlocal fake_now
        fake_now += seconds

    with (
        patch("chat.clients.pydantic_ai.asyncio.sleep", side_effect=fake_sleep),
        patch("chat.clients.pydantic_ai.time.monotonic", side_effect=lambda: fake_now),
    ):
        events = [event async for event in service._wait_for_history_summary()]

    # Keep-alive at t=0, τ ... until the claim has been dead for the full grace.
    assert len(events) == (
        HISTORY_SUMMARY_CLAIM_DEAD_GRACE_SECONDS // HISTORY_SUMMARY_POLL_INTERVAL_SECONDS
    )
    assert all(e.data == [{"type": "keep_alive"}] for e in events)


@pytest.mark.asyncio
async def test_wait_for_history_summary_waits_for_claim_grace_deadline():
    """No live claim: the wait holds until both the deadline and the dead grace pass."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    fake_now = 0.0

    async def fake_sleep(seconds):
        """Patched sleep that advances the fake monotonic clock."""
        nonlocal fake_now
        fake_now += seconds

    # Deadline three poll intervals out, but the claim-dead grace is longer, so
    # the grace is what ends the wait.
    claim_deadline = 3 * HISTORY_SUMMARY_POLL_INTERVAL_SECONDS
    assert claim_deadline < HISTORY_SUMMARY_CLAIM_DEAD_GRACE_SECONDS
    with (
        patch("chat.clients.pydantic_ai.asyncio.sleep", side_effect=fake_sleep),
        patch("chat.clients.pydantic_ai.time.monotonic", side_effect=lambda: fake_now),
    ):
        events = [
            event
            async for event in service._wait_for_history_summary(claim_deadline=claim_deadline)
        ]

    assert len(events) == (
        HISTORY_SUMMARY_CLAIM_DEAD_GRACE_SECONDS // HISTORY_SUMMARY_POLL_INTERVAL_SECONDS
    )
    assert all(e.data == [{"type": "keep_alive"}] for e in events)


@pytest.mark.asyncio
async def test_wait_for_history_summary_survives_a_celery_retry_gap():
    """A claim dropped between Celery retries must not end the wait."""
    conversation = await sync_to_async(ChatConversationFactory)(
        history_summary_claimed_at=timezone.now(),
    )
    service = AIAgentService(conversation, user=conversation.owner)
    fake_now = 0.0
    ticks = 0

    async def fake_sleep(seconds):
        """Drop the claim as a retry would, then re-claim and land the summary."""
        nonlocal fake_now, ticks
        fake_now += seconds
        ticks += 1
        update = type(conversation).objects.filter(pk=conversation.pk).update
        if ticks == 1:
            # Provider blip: the task released its claim on the way to a retry.
            await sync_to_async(update)(history_summary_claimed_at=None)
        elif ticks == 2:
            # The retry ran and re-claimed well inside the grace.
            await sync_to_async(update)(history_summary_claimed_at=timezone.now())
        elif ticks == 3:
            await sync_to_async(update)(history_summary="retried", history_summary_checkpoint=9)

    with (
        patch("chat.clients.pydantic_ai.asyncio.sleep", side_effect=fake_sleep),
        patch("chat.clients.pydantic_ai.time.monotonic", side_effect=lambda: fake_now),
    ):
        events = [event async for event in service._wait_for_history_summary()]

    # Without the grace the wait would end at the second poll, on the dropped
    # claim, and the turn would fail while the retry was about to succeed.
    assert len(events) == 3
    assert service.conversation.history_summary_checkpoint == 9


@pytest.mark.asyncio
async def test_wait_for_history_summary_grace_ends_early_when_summary_lands():
    """A checkpoint advance ends the grace wait immediately."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    fake_now = 0.0

    async def fake_sleep(seconds):
        """Patched sleep that lands the summary on the first poll tick."""
        nonlocal fake_now
        first_tick = fake_now == 0.0
        fake_now += seconds
        if first_tick:
            await sync_to_async(type(conversation).objects.filter(pk=conversation.pk).update)(
                history_summary="landed", history_summary_checkpoint=6
            )

    with (
        patch("chat.clients.pydantic_ai.asyncio.sleep", side_effect=fake_sleep),
        patch("chat.clients.pydantic_ai.time.monotonic", side_effect=lambda: fake_now),
    ):
        events = [event async for event in service._wait_for_history_summary(claim_deadline=30.0)]

    assert len(events) == 1
    assert service.conversation.history_summary_checkpoint == 6


@contextmanager
def _run_agent_patches(service):
    """The boilerplate patch stack for driving the real _run_agent."""

    async def fake_prepare(_messages):
        """Return a stub agent-run preparation tuple."""
        usage = {"promptTokens": 0, "completionTokens": 0, "co2_impact": 0}
        return ("prompt", [], [], [], usage, [], False)

    async def fake_handle_docs(*_args, **_kwargs):
        """Yield a stub document-parsing result with no documents."""
        yield DocumentParsingResult(success=True, has_documents=False)

    @asynccontextmanager
    async def fake_iter(*_args, **_kwargs):
        """Yield a fake agent run as an async context manager."""
        yield _FakeRun()

    service.conversation_agent = MagicMock()
    service.conversation_agent.iter = fake_iter

    patches = (
        patch.object(service, "_prepare_agent_run", side_effect=fake_prepare),
        patch.object(service, "_handle_input_documents", side_effect=fake_handle_docs),
        patch.object(service, "_build_model_history", return_value=[]),
        patch.object(service, "_agent_stop_streaming", AsyncMock()),
        patch.object(service, "_setup_self_documentation_tool"),
        patch.object(service, "_setup_web_search_tool"),
        patch.object(service, "_setup_web_search"),
        patch.object(service, "_check_should_enable_rag", AsyncMock(return_value=False)),
        patch.object(service, "_process_agent_nodes", side_effect=_empty_async_gen),
        patch.object(service, "_finalize_conversation", side_effect=_empty_async_gen),
        patch("chat.clients.pydantic_ai.get_mcp_servers", return_value=[]),
        patch("chat.clients.pydantic_ai._extract_co2_from_usage", return_value=0),
    )
    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        yield


@pytest.mark.asyncio
async def test_run_agent_enqueues_task_and_adopts_its_summary(ui_messages):
    """The over-budget turn enqueues the Celery task, waits, and adopts the result."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    async def fake_wait(claim_deadline=None):  # pylint: disable=unused-argument
        """Fake wait that lands a summary on the conversation while the turn waits."""
        # Simulate the task completing while the turn waited.
        await sync_to_async(type(conversation).objects.filter(pk=conversation.pk).update)(
            history_summary="task summary", history_summary_checkpoint=6
        )
        await service.conversation.arefresh_from_db()
        if False:  # pragma: no cover - never yields, only makes this a generator
            yield

    # True at turn start (phase triggers), False after adopting the summary.
    should_generate = MagicMock(side_effect=[True, False])

    with (
        _run_agent_patches(service),
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            should_generate,
        ),
        patch("chat.clients.pydantic_ai.summarize_conversation_history") as task,
        patch.object(service, "_wait_for_history_summary", side_effect=fake_wait),
    ):
        events = [event async for event in service._run_agent(ui_messages)]

    task.delay.assert_called_once_with(str(conversation.pk))
    assert service._history_summary == "task summary"
    assert service._history_summary_checkpoint == 6
    tool_results = [e for e in events if isinstance(e, events_v4.ToolResultPart)]
    assert [r.result for r in tool_results] == [{"state": "done"}]


@pytest.mark.asyncio
async def test_run_agent_does_not_enqueue_when_claim_is_live(ui_messages):
    """Another actor is already summarizing: wait for it, never double-enqueue."""
    conversation = await sync_to_async(ChatConversationFactory)(
        history_summary_claimed_at=timezone.now(),
    )
    service = AIAgentService(conversation, user=conversation.owner)

    async def fake_wait(claim_deadline=None):  # pylint: disable=unused-argument
        """Fake wait that lands a summary on the conversation while the turn waits."""
        await sync_to_async(type(conversation).objects.filter(pk=conversation.pk).update)(
            history_summary="from the other actor",
            history_summary_checkpoint=6,
            history_summary_claimed_at=None,
        )
        await service.conversation.arefresh_from_db()
        if False:  # pragma: no cover
            yield

    should_generate = MagicMock(side_effect=[True, False])

    with (
        _run_agent_patches(service),
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            should_generate,
        ),
        patch("chat.clients.pydantic_ai.summarize_conversation_history") as task,
        patch.object(service, "_wait_for_history_summary", side_effect=fake_wait),
    ):
        _ = [event async for event in service._run_agent(ui_messages)]

    task.delay.assert_not_called()
    assert service._history_summary == "from the other actor"


@pytest.mark.asyncio
async def test_run_agent_fails_when_summary_never_lands(ui_messages):
    """Grace expires with nothing landed and still over budget: the turn fails, no degraded turn."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    # Still over budget at turn start AND after the fruitless wait.
    should_generate = MagicMock(side_effect=[True, True])

    with (
        _run_agent_patches(service),
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            should_generate,
        ),
        patch("chat.clients.pydantic_ai.summarize_conversation_history") as task,
        patch.object(service, "_wait_for_history_summary", side_effect=_empty_async_gen),
    ):
        with pytest.raises(SummarizationRequiredError):
            _ = [event async for event in service._run_agent(ui_messages)]

    task.delay.assert_called_once_with(str(conversation.pk))


def _captured_events(mock_posthog):
    """The PostHog event names captured, in order."""
    return [call.args[0] for call in mock_posthog.capture.call_args_list]


@pytest.mark.asyncio
async def test_run_agent_captures_the_summarization_funnel(ui_messages, settings):
    """A summarized turn reports its start and its success, attributed to the user."""
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    with (
        _run_agent_patches(service),
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            side_effect=[True, False],  # over budget, then the summary lands
        ),
        patch("chat.clients.pydantic_ai.summarize_conversation_history"),
        patch.object(service, "_wait_for_history_summary", side_effect=_empty_async_gen),
        patch("core.analytics.posthog") as mock_posthog,
    ):
        _ = [event async for event in service._run_agent(ui_messages)]

    assert _captured_events(mock_posthog) == [
        "conversation_summarization_started",
        "conversation_summarization_succeeded",
    ]
    success = mock_posthog.capture.call_args_list[1]
    assert success.kwargs["distinct_id"] == str(conversation.owner.pk)
    assert success.kwargs["properties"]["conversation_id"] == str(conversation.pk)
    assert success.kwargs["properties"]["waited_seconds"] >= 0


@pytest.mark.asyncio
async def test_run_agent_captures_the_summarization_failure(ui_messages, settings):
    """A turn that fails for want of a summary reports the failure after the start."""
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    with (
        _run_agent_patches(service),
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            side_effect=[True, True],  # still over budget after the fruitless wait
        ),
        patch("chat.clients.pydantic_ai.summarize_conversation_history"),
        patch.object(service, "_wait_for_history_summary", side_effect=_empty_async_gen),
        patch("core.analytics.posthog") as mock_posthog,
    ):
        with pytest.raises(SummarizationRequiredError):
            _ = [event async for event in service._run_agent(ui_messages)]

    assert _captured_events(mock_posthog) == [
        "conversation_summarization_started",
        "conversation_summarization_failed",
    ]


@pytest.mark.asyncio
async def test_run_agent_captures_nothing_without_summarization(ui_messages, settings):
    """A turn that stays within budget reports no summarization event at all."""
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    with (
        _run_agent_patches(service),
        patch(
            "chat.clients.pydantic_ai.should_generate_conversation_summary",
            return_value=False,
        ),
        patch("core.analytics.posthog") as mock_posthog,
    ):
        _ = [event async for event in service._run_agent(ui_messages)]

    mock_posthog.capture.assert_not_called()
