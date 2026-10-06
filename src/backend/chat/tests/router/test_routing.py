"""Tests for the routing step and RoutingTierSettings."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument

from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from chat.ai_sdk_types import FileUIPart, TextUIPart, UIMessage
from chat.enums import RoutingReason, RoutingTier, TierSource
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.model_health import set_model_health
from chat.models import RoutingTierSettings
from chat.router import RoutingDecision, RoutingLabels, route_turn
from chat.router.routing import (
    last_answer_excerpt,
    last_routing_payload,
    message_has_image,
    previous_labels_from,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("clear_cache"),
]


def _llm(hrid, **overrides) -> LLModel:
    values = {
        "hrid": hrid,
        "model_name": f"{hrid}-name",
        "human_readable_name": hrid,
        "is_active": True,
        "system_prompt": "You are a helpful assistant.",
        "tools": [],
        "provider": LLMProvider(hrid="albert", base_url="https://albert.example/v1", api_key="k"),
    }
    values.update(overrides)
    return LLModel(**values)


@pytest.fixture(autouse=True)
def tier_configuration(settings):
    """Three tiers with alternatives, a text-only model on tier 3."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": _llm("default-model", supports_image=True, web_search="chat.x.y"),
        "small": _llm("small", supports_image=False, max_token_context=1000),
        "small-vision": _llm("small-vision", supports_image=True),
        "medium": _llm("medium", supports_image=True, web_search="chat.x.y"),
        "medium-alt": _llm("medium-alt", supports_image=True),
        "reasoner": _llm("reasoner", supports_image=False),
        "reasoner-vision": _llm("reasoner-vision", supports_image=True),
        "summarizer": _llm("summarizer", role="utility"),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    settings.LLM_ROUTER_MODEL_HRID = ""
    settings.LLM_FALLBACK_MODEL_HRID_1 = ""
    settings.LLM_FALLBACK_MODEL_HRID_2 = ""
    settings.LLM_TIER_SIMPLE_MODEL_HRID = ""
    settings.LLM_TIER_STANDARD_MODEL_HRID = ""
    settings.LLM_TIER_COMPLEX_MODEL_HRID = ""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def tier_settings():
    tier_settings = RoutingTierSettings.get_solo()
    tier_settings.simple_model_hrid = "small"
    tier_settings.simple_alternatives = ["small-vision"]
    tier_settings.standard_model_hrid = "medium"
    tier_settings.standard_alternatives = ["medium-alt"]
    tier_settings.complex_model_hrid = "reasoner"
    tier_settings.complex_alternatives = ["reasoner-vision"]
    tier_settings.save()
    return tier_settings


def labels(complexity=RoutingTier.STANDARD, confidence=0.8):
    return RoutingLabels(complexity=complexity, confidence=confidence)


def classify_returning(labels_, reason=RoutingReason.CLASSIFIED, latency_ms=120):
    async def fake_classify(*_args, **_kwargs):
        return labels_, reason, latency_ms

    return mock.patch("chat.router.routing.classify", side_effect=fake_classify)


def message(text="Rédige une note de trois pages sur la réforme", with_image=False):
    parts = [TextUIPart(type="text", text=text)]
    if with_image:
        parts.append(FileUIPart(type="file", mediaType="image/png", url="data:image/png;base64,AA"))
    return UIMessage(id="u1", role="user", parts=parts)


async def make_conversation(**kwargs):
    """Factories touch the database: run them off the event loop."""
    return await sync_to_async(ChatConversationFactory)(**kwargs)


async def save(instance):
    await sync_to_async(instance.save)()


async def route(conversation, msg=None, **overrides):
    kwargs = {
        "conversation": conversation,
        "message": msg or message(),
        "force_web_search": False,
        "has_attachments": False,
        "has_project_context": False,
        "requested_model_hrid": None,
    }
    kwargs.update(overrides)
    return await route_turn(**kwargs)


# --- RoutingTierSettings -----------------------------------------------------


def test_model_for_falls_back_to_settings_then_default(settings):
    tier_settings = RoutingTierSettings.get_solo()
    assert tier_settings.model_for(RoutingTier.SIMPLE) == "default-model"
    settings.LLM_TIER_SIMPLE_MODEL_HRID = "small"
    assert tier_settings.model_for(RoutingTier.SIMPLE) == "small"
    tier_settings.simple_model_hrid = "small-vision"
    assert tier_settings.model_for("simple") == "small-vision"


def test_alternatives_exclude_the_tier_model_and_all_models_dedupes(tier_settings):
    tier_settings.standard_alternatives = ["medium", "medium-alt", "medium-alt", ""]
    assert tier_settings.alternatives_for(RoutingTier.STANDARD) == ["medium-alt"]
    assert tier_settings.all_models_for(RoutingTier.STANDARD) == ["medium", "medium-alt"]


def test_clean_rejects_unknown_and_utility_models(tier_settings):
    tier_settings.simple_model_hrid = "summarizer"
    tier_settings.complex_alternatives = ["nope"]
    tier_settings.router_model_hrid = "ghost"
    with pytest.raises(ValidationError) as exc:
        tier_settings.clean()
    assert set(exc.value.message_dict) == {
        "simple_model_hrid",
        "complex_alternatives",
        "router_model_hrid",
    }


def test_clean_rejects_alternatives_that_are_not_a_list(tier_settings):
    tier_settings.simple_alternatives = "small-vision"
    with pytest.raises(ValidationError) as exc:
        tier_settings.clean()
    assert set(exc.value.message_dict) == {"simple_alternatives"}


def test_clean_accepts_blank_and_chat_models(tier_settings):
    tier_settings.router_model_hrid = "summarizer"  # any configured model may classify
    tier_settings.clean()


# --- thresholds and tier choice ----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "complexity,confidence,expected",
    [
        (RoutingTier.SIMPLE, 0.95, RoutingTier.SIMPLE),
        (RoutingTier.SIMPLE, 0.5, RoutingTier.STANDARD),
        (RoutingTier.COMPLEX, 0.7, RoutingTier.COMPLEX),
        (RoutingTier.COMPLEX, 0.69, RoutingTier.STANDARD),
        (RoutingTier.STANDARD, 0.1, RoutingTier.STANDARD),
    ],
)
async def test_confidence_threshold_gates_tiers_one_and_three(
    tier_settings, complexity, confidence, expected
):
    conversation = await make_conversation()
    with classify_returning(labels(complexity, confidence)):
        decision = await route(conversation)
    assert decision.tier == expected
    assert decision.tier_source == TierSource.ROUTER
    assert decision.reason == RoutingReason.CLASSIFIED
    assert decision.router_confidence == confidence
    assert decision.router_latency_ms == 120
    assert decision.model_hrid == tier_settings.model_for(expected)


@pytest.mark.asyncio
async def test_admin_threshold_is_used(tier_settings):
    tier_settings.confidence_threshold = 0.95
    await save(tier_settings)
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.SIMPLE, 0.9)):
        decision = await route(conversation)
    assert decision.tier == RoutingTier.STANDARD


@pytest.mark.asyncio
async def test_classifier_runs_on_the_admin_router_model(tier_settings, settings):
    """The admin router model wins over the setting."""
    settings.LLM_ROUTER_MODEL_HRID = "small"
    tier_settings.router_model_hrid = "summarizer"
    await save(tier_settings)
    conversation = await make_conversation()
    with classify_returning(labels()) as classify:
        await route(conversation)
    assert classify.call_args.kwargs["model_hrid"] == "summarizer"


@pytest.mark.asyncio
async def test_classifier_fallback_reason_is_kept(tier_settings):
    conversation = await make_conversation(model_hrid="medium")
    with classify_returning(labels(RoutingTier.STANDARD, 0.0), reason=RoutingReason.FALLBACK):
        decision = await route(conversation)
    assert decision.reason == RoutingReason.FALLBACK
    assert decision.tier == RoutingTier.STANDARD
    assert decision.previous_model_hrid == "medium"
    assert decision.changed is False


@pytest.mark.asyncio
async def test_no_op_when_nothing_is_configured(settings):
    """Blank tiers all resolve to the default model: the router changes nothing."""
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.SIMPLE, 0.99)):
        decision = await route(conversation)
    assert decision.tier == RoutingTier.SIMPLE
    assert decision.model_hrid == settings.LLM_DEFAULT_MODEL_HRID


# --- pinned tier ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_pinned_tier_runs_the_tier_model_without_classifying(tier_settings):
    conversation = await make_conversation(pinned_tier=RoutingTier.COMPLEX, model_hrid="small")
    with mock.patch("chat.router.routing.classify") as classify:
        decision = await route(conversation)
    classify.assert_not_called()
    assert decision.tier == RoutingTier.COMPLEX
    assert decision.tier_source == TierSource.USER
    assert decision.reason == RoutingReason.USER_PINNED
    assert decision.model_hrid == "reasoner"
    assert decision.labels is None
    assert decision.router_confidence is None
    assert decision.changed is True


@pytest.mark.asyncio
async def test_pinned_tier_still_walks_the_constraints(tier_settings):
    """Constraints are capabilities, not preferences: they apply to a pin too."""
    conversation = await make_conversation(pinned_tier=RoutingTier.COMPLEX)
    decision = await route(conversation, message(with_image=True))
    assert decision.model_hrid == "reasoner-vision"
    assert decision.tier_source == TierSource.USER


# --- constraints -----------------------------------------------------------------


def test_message_has_image():
    assert message_has_image(message(with_image=True)) is True
    assert message_has_image(message()) is False
    assert message_has_image(None) is False


@pytest.mark.asyncio
async def test_image_walks_to_the_vision_alternative_of_the_same_tier(tier_settings):
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.SIMPLE, 0.9)):
        decision = await route(conversation, message(with_image=True))
    assert decision.tier == RoutingTier.SIMPLE
    assert decision.model_hrid == "small-vision"
    assert decision.tier_source == TierSource.ROUTER  # same tier: no bump


@pytest.mark.asyncio
async def test_constraint_walks_up_to_the_next_tier(tier_settings):
    tier_settings.simple_alternatives = []
    await save(tier_settings)
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.SIMPLE, 0.9)):
        decision = await route(conversation, message(with_image=True))
    assert decision.tier == RoutingTier.STANDARD
    assert decision.model_hrid == "medium"
    assert decision.tier_source == TierSource.CONSTRAINT
    assert decision.reason == RoutingReason.CONSTRAINT


@pytest.mark.asyncio
async def test_forced_web_search_needs_a_model_with_web_search(tier_settings):
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.SIMPLE, 0.9)):
        decision = await route(conversation, force_web_search=True)
    assert decision.model_hrid == "medium"
    assert decision.tier == RoutingTier.STANDARD
    assert decision.reason == RoutingReason.CONSTRAINT


def stored_history(*texts):
    """Stored ``pydantic_messages`` alternating user prompts and assistant answers."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content=text)])
        if index % 2 == 0
        else ModelResponse(parts=[TextPart(content=text)])
        for index, text in enumerate(texts)
    ]
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")


@pytest.mark.asyncio
async def test_context_length_walks_to_a_larger_model(tier_settings):
    conversation = await make_conversation(pydantic_messages=stored_history("cat " * 2000))
    with classify_returning(labels(RoutingTier.SIMPLE, 0.9)):
        decision = await route(conversation)
    # "small" has a 1000 token context; the history is about 2000 tokens.
    assert decision.model_hrid == "small-vision"
    assert decision.tier == RoutingTier.SIMPLE


@pytest.mark.asyncio
async def test_context_length_ignores_the_summarized_history(tier_settings, settings):
    """Only the summary and the window after the checkpoint count, as at runtime."""
    settings.CONVERSATION_SUMMARY_CONTEXT_MESSAGES = 2
    conversation = await make_conversation(
        pydantic_messages=stored_history(
            "cat " * 2000, "réponse " * 2000, "Bonjour", "Salut", "Merci", "De rien"
        ),
        history_summary="Résumé court.",
        history_summary_checkpoint=4,
    )
    with classify_returning(labels(RoutingTier.SIMPLE, 0.9)):
        decision = await route(conversation)
    assert decision.model_hrid == "small"
    assert decision.reason == RoutingReason.CLASSIFIED


@pytest.mark.asyncio
async def test_constraint_fallback_uses_the_default_model(tier_settings, settings):
    """No tier model can read images when web search is also forced: default model."""
    for hrid in ("small-vision", "medium", "medium-alt", "reasoner-vision"):
        settings.LLM_CONFIGURATIONS[hrid].web_search = None
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.STANDARD, 0.9)):
        decision = await route(conversation, message(with_image=True), force_web_search=True)
    assert decision.model_hrid == "default-model"
    assert decision.reason == RoutingReason.CONSTRAINT_FALLBACK
    assert decision.tier_source == TierSource.CONSTRAINT
    assert decision.tier == RoutingTier.STANDARD


# --- health cascade ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_red_tier_model_cascades_to_its_alternative(tier_settings):
    set_model_health("albert", "medium-name", "red")
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.STANDARD, 0.9)):
        decision = await route(conversation)
    assert decision.model_hrid == "medium-alt"
    assert decision.tier == RoutingTier.STANDARD


@pytest.mark.asyncio
async def test_red_tier_model_then_settings_fallback(tier_settings, settings):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "default-model"
    tier_settings.standard_alternatives = []
    await save(tier_settings)
    set_model_health("albert", "medium-name", "red")
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.STANDARD, 0.9)):
        decision = await route(conversation)
    assert decision.model_hrid == "default-model"


@pytest.mark.asyncio
async def test_everything_red_keeps_the_tier_model(tier_settings):
    set_model_health("albert", "medium-name", "red")
    set_model_health("albert", "medium-alt-name", "red")
    conversation = await make_conversation()
    with classify_returning(labels(RoutingTier.STANDARD, 0.9)):
        decision = await route(conversation)
    assert decision.model_hrid == "medium"


# --- model picker ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requested_model_is_used_as_is(tier_settings):
    conversation = await make_conversation()
    with mock.patch("chat.router.routing.classify") as classify:
        decision = await route(conversation, requested_model_hrid="reasoner-vision")
    classify.assert_not_called()
    assert decision.model_hrid == "reasoner-vision"
    assert decision.tier == RoutingTier.COMPLEX
    assert decision.tier_source == TierSource.USER
    assert decision.reason == RoutingReason.USER_PINNED


@pytest.mark.asyncio
async def test_requested_model_outside_the_tiers_reports_standard(tier_settings):
    conversation = await make_conversation()
    decision = await route(conversation, requested_model_hrid="default-model")
    assert decision.model_hrid == "default-model"
    assert decision.tier == RoutingTier.STANDARD


# --- previous turn hints -----------------------------------------------------------------


def test_last_routing_round_trip():
    conversation = ChatConversationFactory()
    assert previous_labels_from(conversation) is None

    decision = RoutingDecision(
        tier=RoutingTier.COMPLEX,
        tier_source=TierSource.ROUTER,
        model_hrid="reasoner",
        labels=labels(RoutingTier.COMPLEX, 0.8),
        reason=RoutingReason.CLASSIFIED,
    )
    conversation.last_routing = last_routing_payload(decision)
    assert conversation.last_routing == {
        "tier": "complex",
        "model_hrid": "reasoner",
        "labels": {"complexity": "complex", "confidence": 0.8},
    }
    assert previous_labels_from(conversation) == decision.labels

    conversation.last_routing = {"labels": {"complexity": "nope"}}
    assert previous_labels_from(conversation) is None


def test_last_answer_excerpt_takes_the_tail_of_the_last_assistant_message():
    conversation = ChatConversationFactory(
        ui_messages=[
            {"role": "assistant", "parts": [{"type": "text", "text": "first"}]},
            {"role": "assistant", "parts": [{"type": "text", "text": "x" * 1000}]},
            {"role": "user", "parts": [{"type": "text", "text": "question"}]},
        ]
    )
    excerpt = last_answer_excerpt(conversation)
    assert excerpt == "x" * 800
    assert last_answer_excerpt(ChatConversationFactory(ui_messages=[])) is None


@pytest.mark.asyncio
async def test_previous_turn_and_context_reach_the_classifier(tier_settings):
    previous = labels(RoutingTier.COMPLEX, 0.9)
    conversation = await make_conversation(
        last_routing={"tier": "complex", "labels": previous.model_dump(mode="json")},
        ui_messages=[{"role": "assistant", "parts": [{"type": "text", "text": "the end"}]}],
    )
    with classify_returning(labels()) as classify:
        await route(conversation, has_attachments=True, has_project_context=True)
    classify.assert_called_once()
    args = classify.call_args.args
    assert args[1] == previous
    assert args[2] == "the end"
    assert args[3] is True
    assert args[4] is True
