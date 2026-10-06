"""Routing step: turn the classifier labels into a model for the turn.

```
labels = classify(message, previous_labels, context)
tier   = pinned_tier or (labels.complexity if labels.confidence >= threshold else "standard")
tier   = max(tier, minimum_tier_for(constraints))     # image, context length, web search
model  = resolve(tier)  ->  health cascade (chat/model_routing.py)
```
"""

import dataclasses
import logging

from django.conf import settings

from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelMessagesTypeAdapter

from chat import models
from chat.agents.history_processors import (
    _estimate_history_tokens,
    build_active_history,
    safe_clean_tool_history,
)
from chat.ai_sdk_types import FileUIPart, TextUIPart, UIMessage
from chat.constants import IMAGE_MIME_PREFIX
from chat.enums import RoutingReason, RoutingTier, TierSource
from chat.llm_configuration import LLModel
from chat.model_routing import first_healthy
from chat.tokens import count_approx_tokens

from .classifier import PREVIOUS_ANSWER_MAX_CHARS, classify, router_model_hrid
from .labels import RoutingDecision, RoutingLabels

logger = logging.getLogger(__name__)

TIER_ORDER = [RoutingTier.SIMPLE, RoutingTier.STANDARD, RoutingTier.COMPLEX]


@dataclasses.dataclass(frozen=True)
class TurnConstraints:
    """Hard capabilities the model of this turn must have: never route below them."""

    needs_image: bool = False
    needs_web_search: bool = False
    context_tokens: int = 0

    def satisfied_by(self, configuration: LLModel | None) -> bool:
        """Whether an active configured model can serve this turn."""
        if configuration is None or not configuration.is_active:
            return False
        if self.needs_image and not configuration.supports_image:
            return False
        if self.needs_web_search and not configuration.web_search:
            return False
        if (
            configuration.max_token_context is not None
            and self.context_tokens > configuration.max_token_context
        ):
            return False
        return True


# --------------------------------------------------------------------------- #
# Conversation helpers (what the previous turn left behind)
# --------------------------------------------------------------------------- #


def message_text(message: UIMessage) -> str:
    """Plain text of a UI message: its text parts, else its legacy ``content``."""
    texts = [part.text for part in message.parts or [] if isinstance(part, TextUIPart)]
    if texts:
        return "\n".join(texts)
    return message.content or ""


def message_has_file(message: UIMessage | None) -> bool:
    """Whether the user message carries any file attachment."""
    if message is None:
        return False
    return any(isinstance(part, FileUIPart) for part in message.parts or [])


def message_has_image(message: UIMessage | None) -> bool:
    """Whether the user message carries at least one image attachment."""
    if message is None:
        return False
    return any(
        isinstance(part, FileUIPart) and (part.mediaType or "").startswith(IMAGE_MIME_PREFIX)
        for part in message.parts or []
    )


def previous_labels_from(conversation: models.ChatConversation) -> RoutingLabels | None:
    """Labels recorded by the previous turn's routing decision, if any."""
    raw = (conversation.last_routing or {}).get("labels")
    if not raw:
        return None
    try:
        return RoutingLabels.model_validate(raw)
    except ValueError:
        logger.debug("Ignoring unreadable previous routing labels", exc_info=True)
        return None


def last_answer_excerpt(conversation: models.ChatConversation) -> str | None:
    """Tail of the last assistant answer sent back by the frontend (``ui_messages``)."""
    for raw in reversed(conversation.ui_messages or []):
        if not isinstance(raw, dict) or raw.get("role") != "assistant":
            continue
        texts = [
            part.get("text", "")
            for part in raw.get("parts") or []
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        text = "\n".join(texts) if texts else (raw.get("content") or "")
        return text[-PREVIOUS_ANSWER_MAX_CHARS:] or None
    return None


def estimate_history_tokens(conversation: models.ChatConversation, message: UIMessage) -> int:
    """Rough token count of what the model will read: summary, active history and this message.

    Mirrors the runtime (``_build_model_history``): the summarized prefix is replaced by
    the persisted summary, only the window from the summary checkpoint on is sent.
    """
    try:
        history = ModelMessagesTypeAdapter.validate_python(conversation.pydantic_messages or [])
    except ValueError:
        logger.debug("Ignoring unreadable stored history for the context estimate", exc_info=True)
        history = []
    active_history = build_active_history(
        safe_clean_tool_history(history),
        max(conversation.history_summary_checkpoint, 0),
        settings.CONVERSATION_SUMMARY_CONTEXT_MESSAGES,
    )
    return (
        _estimate_history_tokens(active_history)
        + count_approx_tokens(conversation.history_summary or "")
        + count_approx_tokens(message_text(message))
    )


def _conversation_has_image(conversation: models.ChatConversation) -> bool:
    return conversation.attachments.filter(
        content_type__startswith=IMAGE_MIME_PREFIX,
        upload_state=models.AttachmentStatus.READY,
    ).exists()


# --------------------------------------------------------------------------- #
# Tier and model resolution
# --------------------------------------------------------------------------- #


def tier_from_labels(labels: RoutingLabels, threshold: float) -> RoutingTier:
    """Tiers 1 and 3 are chosen only at or above the confidence threshold."""
    if labels.complexity == RoutingTier.STANDARD or labels.confidence >= threshold:
        return labels.complexity
    return RoutingTier.STANDARD


def tier_of_model(tier_settings: models.RoutingTierSettings, model_hrid: str) -> RoutingTier | None:
    """Lowest tier whose model or alternatives include ``model_hrid``."""
    for tier in TIER_ORDER:
        if model_hrid in tier_settings.all_models_for(tier):
            return tier
    return None


def _fitting_models(
    tier_settings: models.RoutingTierSettings, tier: RoutingTier, constraints: TurnConstraints
) -> list[str]:
    return [
        hrid
        for hrid in tier_settings.all_models_for(tier)
        if constraints.satisfied_by(settings.LLM_CONFIGURATIONS.get(hrid))
    ]


def resolve_model(
    tier_settings: models.RoutingTierSettings, tier: RoutingTier, constraints: TurnConstraints
) -> tuple[RoutingTier, str, bool]:
    """Walk up from ``tier`` to the first tier with a model that fits, then cascade on health.

    Returns ``(tier, model_hrid, fell_back)``. ``fell_back`` is True when no tier
    model fits and the default model is used (reason ``constraint_fallback``).
    """
    for candidate_tier in TIER_ORDER[TIER_ORDER.index(tier) :]:
        candidates = _fitting_models(tier_settings, candidate_tier, constraints)
        if not candidates:
            continue
        # The existing fallback settings remain the health cascade for each tier.
        for fb_hrid in (settings.LLM_FALLBACK_MODEL_HRID_1, settings.LLM_FALLBACK_MODEL_HRID_2):
            if (
                fb_hrid
                and fb_hrid not in candidates
                and constraints.satisfied_by(settings.LLM_CONFIGURATIONS.get(fb_hrid))
            ):
                candidates.append(fb_hrid)
        return candidate_tier, first_healthy(candidates), False

    logger.warning(
        "No tier model satisfies the turn constraints %s; using the default", constraints
    )
    return tier, settings.LLM_DEFAULT_MODEL_HRID, True


async def route_turn(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    *,
    conversation: models.ChatConversation,
    message: UIMessage,
    force_web_search: bool,
    has_attachments: bool,
    has_project_context: bool,
    requested_model_hrid: str | None,
) -> RoutingDecision:
    """Decide the tier and model of one turn.

    A pinned tier (``conversation.pinned_tier``) bypasses the classifier. A
    ``requested_model_hrid`` (model picker, validated by the request serializer)
    is used as is. Constraints and the health cascade apply in every other case.
    """
    tier_settings = await sync_to_async(models.RoutingTierSettings.get_solo)()
    previous_model_hrid = conversation.model_hrid or None

    if requested_model_hrid:
        return RoutingDecision(
            tier=tier_of_model(tier_settings, requested_model_hrid) or RoutingTier.STANDARD,
            tier_source=TierSource.USER,
            model_hrid=requested_model_hrid,
            reason=RoutingReason.USER_PINNED,
            previous_model_hrid=previous_model_hrid,
        )

    if conversation.pinned_tier:
        tier = RoutingTier(conversation.pinned_tier)
        tier_source, reason = TierSource.USER, RoutingReason.USER_PINNED
        labels, confidence, latency_ms = None, None, 0
    else:
        labels, reason, latency_ms = await classify(
            message_text(message),
            previous_labels_from(conversation),
            last_answer_excerpt(conversation),
            has_attachments,
            has_project_context,
            model_hrid=router_model_hrid(tier_settings.router_model_hrid),
        )
        tier = tier_from_labels(labels, tier_settings.confidence_threshold)
        tier_source, confidence = TierSource.ROUTER, labels.confidence

    constraints = TurnConstraints(
        needs_image=message_has_image(message)
        or await sync_to_async(_conversation_has_image)(conversation),
        needs_web_search=force_web_search,
        context_tokens=estimate_history_tokens(conversation, message),
    )
    # ``resolve_model`` ends on the health cascade, which reads the model-health
    # singleton from the database, so it must not run on the event loop.
    resolved_tier, model_hrid, fell_back = await sync_to_async(resolve_model)(
        tier_settings, tier, constraints
    )
    if fell_back:
        tier_source, reason = TierSource.CONSTRAINT, RoutingReason.CONSTRAINT_FALLBACK
    elif resolved_tier != tier:
        tier, tier_source, reason = resolved_tier, TierSource.CONSTRAINT, RoutingReason.CONSTRAINT

    decision = RoutingDecision(
        tier=tier,
        tier_source=tier_source,
        model_hrid=model_hrid,
        labels=labels,
        reason=reason,
        router_confidence=confidence,
        router_latency_ms=latency_ms,
        previous_model_hrid=previous_model_hrid,
    )
    logger.debug(
        "Routed turn tier=%s source=%s model=%s reason=%s",
        decision.tier.value,
        decision.tier_source.value,
        decision.model_hrid,
        decision.reason.value,
    )
    return decision


def last_routing_payload(decision: RoutingDecision) -> dict:
    """What ``ChatConversation.last_routing`` keeps for the next turn's hint."""
    return {
        "tier": decision.tier.value,
        "model_hrid": decision.model_hrid,
        "labels": decision.labels.model_dump(mode="json") if decision.labels else None,
    }
