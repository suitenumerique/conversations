"""Tests for co2_impact accumulation in AIAgentService."""

# pylint: disable=protected-access
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart

from chat.clients.pydantic_ai import AIAgentService, StreamingState
from chat.vercel_ai_sdk.core import events_v4


def _fake_sync_to_async(fn):
    """Replacement for sync_to_async: runs the callable directly (no thread pool)."""

    async def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


@pytest.fixture(name="conversation")
def conversation_fixture():
    """Return a minimal mock conversation (no DB required)."""
    conv = MagicMock()
    conv.messages = []
    conv.pydantic_messages = []
    conv.agent_usage = {}
    conv.title_set_by_user_at = None
    return conv


@pytest.fixture(name="service")
def service_fixture(conversation):
    """Instantiate AIAgentService without __init__, injecting only the conversation."""
    s = object.__new__(AIAgentService)
    s.conversation = conversation
    return s


@pytest.fixture(name="final_output")
def final_output_fixture():
    """Minimal model response for _prepare_update_conversation calls."""
    return [ModelResponse(parts=[TextPart(content="Hello")], kind="response")]


# --- _prepare_update_conversation: per-message annotation ---


@pytest.mark.parametrize("co2_impact", [500, 123])
def test_co2_annotation_added_when_nonzero(conversation, service, final_output, co2_impact):
    """An annotation with the co2_impact value is added to the assistant message."""
    service._prepare_update_conversation(
        final_output=final_output,
        usage={"promptTokens": 10, "completionTokens": 5, "co2_impact": co2_impact},
        model_response_message_id="msg-1",
    )

    assistant_msg = conversation.messages[-1]
    assert {"co2_impact": pytest.approx(float(co2_impact))} in (assistant_msg.annotations or [])


def test_no_co2_annotation_when_zero(conversation, service, final_output):
    """No co2_impact annotation is added when co2_impact is 0."""
    service._prepare_update_conversation(
        final_output=final_output,
        usage={"promptTokens": 10, "completionTokens": 5, "co2_impact": 0},
        model_response_message_id="msg-1",
    )

    assistant_msg = conversation.messages[-1]
    co2_annotations = [a for a in (assistant_msg.annotations or []) if "co2_impact" in a]
    assert co2_annotations == []


# --- _prepare_update_conversation: cumulative usage across runs ---


@pytest.mark.parametrize(
    "run1,run2,expected",
    [
        pytest.param(
            {"promptTokens": 10, "completionTokens": 5, "co2_impact": 1.5e-9},
            {"promptTokens": 12, "completionTokens": 6, "co2_impact": 2.3e-9},
            {"co2_impact": 1.5e-9 + 2.3e-9, "promptTokens": 22, "completionTokens": 11},
            id="both_runs_have_co2",
        ),
        pytest.param(
            {"promptTokens": 10, "completionTokens": 5, "co2_impact": 1.5e-9},
            {"promptTokens": 10, "completionTokens": 5, "co2_impact": 0},
            {"co2_impact": 1.5e-9, "promptTokens": 20, "completionTokens": 10},
            id="second_run_has_no_co2",
        ),
    ],
)
def test_usage_accumulates_across_runs(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # noqa: PLR0913
    conversation,
    service,
    final_output,
    run1,
    run2,
    expected,
):
    """agent_usage accumulates tokens and co2_impact across runs."""
    service._prepare_update_conversation(
        final_output=final_output, usage=run1, model_response_message_id="msg-1"
    )
    service._prepare_update_conversation(
        final_output=final_output, usage=run2, model_response_message_id="msg-2"
    )

    for key, value in expected.items():
        assert conversation.agent_usage[key] == pytest.approx(value), (
            f"agent_usage[{key!r}] mismatch"
        )


# --- _finalize_conversation: FinishMessagePart co2_impact ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "co2_impact",
    [
        pytest.param(300, id="co2_nonzero"),
        pytest.param(0, id="co2_zero"),
    ],
)
async def test_finalize_emits_finish_message_with_co2(service, co2_impact):
    """FinishMessagePart always emitted with co2_impact in usage."""
    service._langfuse_available = False
    usage = {"promptTokens": 10, "completionTokens": 5, "co2_impact": co2_impact}
    state = StreamingState(model_response_message_id="test-msg-id")

    with (
        patch.object(service, "_agent_stop_streaming", new=AsyncMock()),
        patch.object(service, "_prepare_update_conversation"),
        patch("chat.clients.pydantic_ai.sync_to_async", side_effect=_fake_sync_to_async),
    ):
        events = [
            event
            async for event in service._finalize_conversation(
                new_messages=[], run_output="Hello", usage=usage, state=state, image_key_mapping={}
            )
        ]

    finish_events = [e for e in events if isinstance(e, events_v4.FinishMessagePart)]
    assert len(finish_events) == 1
    assert finish_events[0].usage.co2_impact == co2_impact
