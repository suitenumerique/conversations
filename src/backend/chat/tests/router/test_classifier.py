"""Tests for the router classifier."""

import asyncio
from unittest import mock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from chat.enums import RoutingReason, RoutingTier, TierSource
from chat.router import RoutingDecision, RoutingLabels, classify
from chat.router.classifier import (
    FALLBACK_LABELS,
    RouterClassifierAgent,
    build_user_prompt,
    router_model_hrid,
)
from chat.router.prompts import ROUTER_PROMPT

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def generous_router_timeout(settings):
    """Keep the model-call timeout out of the way; timeout tests lower it explicitly."""
    settings.LLM_ROUTER_TIMEOUT_S = 5


PREVIOUS = RoutingLabels(complexity=RoutingTier.COMPLEX, confidence=0.8)


def model_returns(labels: dict):
    """FunctionModel callback answering with `labels` as structured output."""

    def respond(_messages, info):
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=labels)])

    return respond


def agent_with(model):
    """Return a builder yielding a real RouterClassifierAgent with a swapped model."""

    def build(model_hrid):
        agent = RouterClassifierAgent(model_hrid=model_hrid)
        agent._model = model  # pylint: disable=protected-access
        return agent

    return build


async def slow(_messages, _info):
    """A model slower than any router timeout used in these tests."""
    await asyncio.sleep(1)
    return ModelResponse(parts=[])


async def run_classify(**overrides):
    """Call classify with sensible defaults."""
    kwargs = {
        "message_text": "Explique la procédure de rupture conventionnelle dans le secteur public",
        "previous_labels": None,
        "previous_answer_excerpt": None,
        "has_attachments": False,
        "has_project_context": False,
        "model_hrid": "default-model",
    }
    kwargs.update(overrides)
    return await classify(**kwargs)


# --- shortcuts ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_follow_up_reuses_previous_labels_without_model_call():
    """A short follow-up keeps the previous complexity and skips the model."""
    with mock.patch("chat.router.classifier.build_classifier_agent") as build:
        labels, reason, latency = await run_classify(
            message_text="Et pour les contractuels ?", previous_labels=PREVIOUS
        )
    build.assert_not_called()
    assert reason == RoutingReason.SHORTCUT
    assert latency == 0
    # the previous confidence is kept, so the threshold decision is reproduced
    assert labels == RoutingLabels(complexity=RoutingTier.COMPLEX, confidence=0.8)


@pytest.mark.asyncio
async def test_short_message_with_attachments_calls_the_model():
    """A short message with attachments is classified, never a shortcut."""
    builder = agent_with(FunctionModel(model_returns({"complexity": "complex", "confidence": 0.9})))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        labels, reason, _ = await run_classify(
            message_text="analyse ce document",
            previous_labels=RoutingLabels(complexity=RoutingTier.SIMPLE, confidence=0.9),
            has_attachments=True,
        )
    assert reason == RoutingReason.CLASSIFIED
    assert labels.complexity == RoutingTier.COMPLEX


@pytest.mark.asyncio
async def test_short_message_without_previous_labels_calls_the_model():
    """Without previous labels, even a short message is classified."""
    builder = agent_with(FunctionModel(model_returns({"complexity": "simple", "confidence": 0.95})))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        labels, reason, _ = await run_classify(message_text="Bonjour !")
    assert reason == RoutingReason.CLASSIFIED
    assert labels.complexity == RoutingTier.SIMPLE


@pytest.mark.asyncio
async def test_six_word_message_is_not_a_shortcut():
    """The shortcut only applies below six words."""
    builder = agent_with(
        FunctionModel(model_returns({"complexity": "standard", "confidence": 0.8}))
    )
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        _, reason, _ = await run_classify(
            message_text="Rédige un mail pour mon équipe", previous_labels=PREVIOUS
        )
    assert reason == RoutingReason.CLASSIFIED


# --- happy path --------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_model_labels_and_latency():
    """The structured output of the model is returned as is."""
    builder = agent_with(
        FunctionModel(model_returns({"complexity": "standard", "confidence": 0.85}))
    )
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder) as build:
        labels, reason, latency = await run_classify(
            previous_labels=PREVIOUS,
            previous_answer_excerpt="x" * 2000,
            has_project_context=True,
        )
    build.assert_called_once_with("default-model")
    assert reason == RoutingReason.CLASSIFIED
    assert labels == RoutingLabels(complexity=RoutingTier.STANDARD, confidence=0.85)
    assert latency >= 0


@pytest.mark.asyncio
async def test_agent_receives_context_in_user_prompt():
    """The previous complexity, answer excerpt and context flags reach the model, bounded."""
    seen = {}

    def respond(messages, info):
        seen["messages"] = messages
        seen["instructions"] = messages[0].instructions
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={"complexity": "simple", "confidence": 1.0},
                )
            ]
        )

    builder = agent_with(FunctionModel(respond))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        await run_classify(
            message_text="cat " * 1500,  # 6000 chars, many words: no shortcut
            previous_labels=PREVIOUS,
            previous_answer_excerpt="A" * 100 + "B" * 800,
            has_attachments=True,
        )
    user_text = "".join(
        part.content for part in seen["messages"][0].parts if hasattr(part, "content")
    )
    assert "Previous turn complexity: complex." in user_text
    excerpt_section = user_text.split("<<<", 1)[1].split(">>>", 1)[0]
    assert "A" not in excerpt_section  # excerpt truncated to its last 800 chars
    assert "B" * 800 in excerpt_section
    message_section = user_text.rsplit("<<<", 1)[1].split(">>>", 1)[0].strip("\n")
    assert len(message_section) == 2000  # message truncated
    assert "Attachments present: yes" in user_text
    assert "Project context present: no" in user_text
    # pydantic-ai normalises trailing whitespace of instructions
    assert seen["instructions"].strip() == ROUTER_PROMPT.strip()


def test_build_user_prompt_without_context():
    """No previous turn: only the flags and the message are sent."""
    text = build_user_prompt("Bonjour", None, None, False, False)
    assert "Previous turn complexity" not in text
    assert "previous assistant answer" not in text
    assert "User message:\n<<<\nBonjour\n>>>" in text


def test_router_model_hrid_prefers_admin_then_setting_then_default(settings):
    """The admin value wins over the setting, which wins over the default model."""
    settings.LLM_ROUTER_MODEL_HRID = "default-summarization-model"
    assert router_model_hrid("other-model") == "other-model"
    assert router_model_hrid("") == "default-summarization-model"

    settings.LLM_ROUTER_MODEL_HRID = ""
    assert router_model_hrid() == settings.LLM_DEFAULT_MODEL_HRID


def test_agent_has_no_tools():
    """The classifier never calls tools."""
    agent = RouterClassifierAgent(model_hrid="default-summarization-model")
    assert agent.configuration.hrid == "default-summarization-model"
    assert not agent.get_tools()
    assert agent.get_system_prompt() == ROUTER_PROMPT


# --- fallbacks ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_falls_back_to_previous_labels(settings):
    """A slow classifier falls back to the previous labels."""
    settings.LLM_ROUTER_TIMEOUT_S = 0.01
    builder = agent_with(FunctionModel(slow))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        labels, reason, latency = await run_classify(previous_labels=PREVIOUS)
    assert reason == RoutingReason.FALLBACK
    assert labels == PREVIOUS
    assert latency >= 10


@pytest.mark.asyncio
async def test_timeout_without_previous_labels_uses_standard_defaults(settings):
    """A slow classifier on a first turn falls back to standard with no confidence."""
    settings.LLM_ROUTER_TIMEOUT_S = 0.01
    builder = agent_with(FunctionModel(slow))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        labels, reason, _ = await run_classify()
    assert reason == RoutingReason.FALLBACK
    assert labels == FALLBACK_LABELS
    assert labels.complexity == RoutingTier.STANDARD
    assert labels.confidence == 0.0


@pytest.mark.asyncio
async def test_model_exception_falls_back():
    """A provider error falls back."""

    def boom(_messages, _info):
        raise RuntimeError("provider down")

    builder = agent_with(FunctionModel(boom))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        labels, reason, _ = await run_classify(previous_labels=PREVIOUS)
    assert reason == RoutingReason.FALLBACK
    assert labels == PREVIOUS


@pytest.mark.asyncio
async def test_invalid_model_output_falls_back():
    """An out-of-range confidence fails validation; after retries the call errors out."""
    builder = agent_with(FunctionModel(model_returns({"complexity": "simple", "confidence": 7})))
    with mock.patch("chat.router.classifier.build_classifier_agent", side_effect=builder):
        labels, reason, _ = await run_classify()
    assert reason == RoutingReason.FALLBACK
    assert labels == FALLBACK_LABELS


@pytest.mark.asyncio
async def test_agent_build_failure_falls_back():
    """A misconfigured router model falls back instead of failing the turn."""
    with mock.patch(
        "chat.router.classifier.build_classifier_agent", side_effect=ValueError("bad config")
    ):
        labels, reason, _ = await run_classify()
    assert reason == RoutingReason.FALLBACK
    assert labels == FALLBACK_LABELS


# --- shared objects ----------------------------------------------------------


def test_routing_labels_validate_confidence_range():
    """Confidence is bounded to [0, 1]."""
    with pytest.raises(ValueError):
        RoutingLabels(complexity=RoutingTier.SIMPLE, confidence=1.5)


def test_routing_decision_serializes_to_plain_values():
    """The decision dumps to JSON-friendly values and its metadata carries no labels."""
    decision = RoutingDecision(
        tier=RoutingTier.STANDARD,
        tier_source=TierSource.ROUTER,
        model_hrid="default-model",
        labels=PREVIOUS,
        reason=RoutingReason.CLASSIFIED,
        router_confidence=0.8,
        router_latency_ms=120,
        previous_model_hrid="other-model",
    )
    dumped = decision.model_dump(mode="json")
    assert dumped["tier"] == "standard"
    assert dumped["tier_source"] == "router"
    assert dumped["labels"] == {"complexity": "complex", "confidence": 0.8}
    assert dumped["reason"] == "classified"
    assert decision.changed is True
    assert decision.metadata() == {
        "tier": "standard",
        "tier_source": "router",
        "router_reason": "classified",
        "router_confidence": 0.8,
        "router_latency_ms": 120,
    }
