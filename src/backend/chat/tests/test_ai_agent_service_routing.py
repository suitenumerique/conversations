"""Routing decision plumbing in AIAgentService: the data part and the message metadata."""

# pylint: disable=protected-access, redefined-outer-name, missing-function-docstring
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart

from chat.clients.pydantic_ai import AIAgentService
from chat.clients.schema import ImagePostRunActions
from chat.enums import RoutingReason, RoutingTier, TierSource
from chat.llm_configuration import LLModel
from chat.router import RoutingDecision, RoutingLabels
from chat.vercel_ai_sdk.core import events_v4, events_v5
from chat.vercel_ai_sdk.encoder.v4_to_v5 import V4ToV5Translator

DECISION = RoutingDecision(
    tier=RoutingTier.COMPLEX,
    tier_source=TierSource.ROUTER,
    model_hrid="m",
    labels=RoutingLabels(complexity=RoutingTier.COMPLEX, confidence=0.93),
    reason=RoutingReason.CLASSIFIED,
    router_confidence=0.93,
    router_latency_ms=210,
    previous_model_hrid="other",
)


@pytest.fixture(name="conversation")
def conversation_fixture():
    conv = MagicMock()
    conv.pk = 42
    conv.messages = []
    conv.pydantic_messages = []
    conv.agent_usage = {}
    return conv


@pytest.fixture(name="service")
def service_fixture(conversation):
    """AIAgentService without __init__, with a routed turn."""
    s = object.__new__(AIAgentService)
    s.conversation = conversation
    s._routing_decision = DECISION
    s.user = SimpleNamespace(pk=1)
    s.conversation_agent = SimpleNamespace(
        configuration=LLModel(
            hrid="m",
            model_name="test:model",
            human_readable_name="M",
            is_active=True,
            system_prompt="hi",
            tools=[],
        )
    )
    s._pre_stream_events = []
    return s


def test_routing_data_part_and_its_v5_translation(service):
    part = service._routing_data_part()
    assert part == {
        "type": "routing",
        "tier": "complex",
        "tier_label": "router.tier.complex",
        "tier_source": "router",
        "changed": True,
    }
    translated = V4ToV5Translator().translate(events_v4.DataPart(data=[part]))
    assert len(translated) == 1
    assert isinstance(translated[0], events_v5.DataPart)
    assert translated[0].type == "data-routing"
    assert translated[0].data == part
    assert translated[0].transient is True


def test_routing_data_part_without_a_model_change_or_a_decision(service):
    service._routing_decision = DECISION.model_copy(update={"previous_model_hrid": "m"})
    assert service._routing_data_part()["changed"] is False

    service._routing_decision = None
    assert service._routing_data_part() is None


@pytest.mark.asyncio
async def test_run_agent_emits_the_routing_part_before_the_model_runs(service):
    """The routing part comes right after the pre-stream events, before any token."""
    service._pre_stream_events = [{"type": "images_skipped"}]
    prepared = ("prompt", [], [], ImagePostRunActions(), {}, [], False)

    async def stop_here(*_args, **_kwargs):
        """Stop the run right after the input documents phase."""
        yield SimpleNamespace(success=False, has_documents=False)

    with (
        patch.object(service, "_prepare_agent_run", AsyncMock(return_value=prepared)),
        patch.object(service, "_handle_input_documents", side_effect=stop_here),
        patch("chat.clients.pydantic_ai.DocumentParsingResult", SimpleNamespace),
    ):
        service._is_document_upload_enabled = False
        events = [
            event
            async for event in service._run_agent(
                [SimpleNamespace(role="user")], force_web_search=False
            )
        ]
    data_types = [
        event.data[0]["type"] for event in events if isinstance(event, events_v4.DataPart)
    ]
    assert data_types == ["images_skipped", "routing"]


def test_routing_metadata_persisted_on_the_assistant_message(conversation, service):
    service._prepare_update_conversation(
        final_output=[ModelResponse(parts=[TextPart(content="Hello")], kind="response")],
        usage={"promptTokens": 10, "completionTokens": 5, "co2_impact": 2e-6},
        model_response_message_id="msg-1",
    )
    assert conversation.messages[-1].metadata == {
        "tier": "complex",
        "tier_source": "router",
        "router_reason": "classified",
        "router_confidence": 0.93,
        "router_latency_ms": 210,
        "co2_impact": pytest.approx(2e-6),
    }


def test_no_routing_metadata_without_a_decision(conversation, service):
    service._routing_decision = None
    service._prepare_update_conversation(
        final_output=[ModelResponse(parts=[TextPart(content="Hello")], kind="response")],
        usage={"promptTokens": 10, "completionTokens": 5, "co2_impact": 0},
        model_response_message_id="msg-1",
    )
    assert not conversation.messages[-1].metadata
