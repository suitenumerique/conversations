"""Router classifier: one structured-output call rating the complexity of the user's turn."""

import asyncio
import dataclasses
import logging
import time

from django.conf import settings

from chat.agents.base import BaseAgent
from chat.enums import RoutingReason, RoutingTier

from .labels import RoutingLabels
from .prompts import ROUTER_PROMPT

logger = logging.getLogger(__name__)

# A message shorter than this (in whitespace-separated words) with previous labels
# and no attachments is treated as a follow-up and reuses them (confidence
# included, so the threshold decision is reproduced) without calling the model.
SHORTCUT_MAX_WORDS = 6
# Bounds on the text sent to the router model; the classifier does not need more.
MESSAGE_MAX_CHARS = 2000
PREVIOUS_ANSWER_MAX_CHARS = 800  # ~200 tokens

FALLBACK_LABELS = RoutingLabels(complexity=RoutingTier.STANDARD, confidence=0.0)


def router_model_hrid(configured_hrid: str = "") -> str:
    """Return the HRID of the model running the classifier.

    ``configured_hrid`` is the admin value; blank falls back to the
    ``LLM_ROUTER_MODEL_HRID`` setting, then to the default model.
    """
    return configured_hrid or settings.LLM_ROUTER_MODEL_HRID or settings.LLM_DEFAULT_MODEL_HRID


@dataclasses.dataclass(init=False)
class RouterClassifierAgent(BaseAgent):
    """Structured-output agent producing `RoutingLabels`. No tools."""

    def __init__(self, *, model_hrid: str, **kwargs):
        super().__init__(
            model_hrid=model_hrid,
            output_type=RoutingLabels,
            retries=kwargs.pop("retries", 1),
            **kwargs,
        )

    def get_tools(self):
        return []

    def get_system_prompt(self):
        return ROUTER_PROMPT


def build_classifier_agent(model_hrid: str) -> RouterClassifierAgent:
    """Build the classifier agent. Kept as a function so tests can swap the model."""
    return RouterClassifierAgent(model_hrid=model_hrid)


def build_user_prompt(
    message_text: str,
    previous_labels: RoutingLabels | None,
    previous_answer_excerpt: str | None,
    has_attachments: bool,
    has_project_context: bool,
) -> str:
    """Assemble the user-side input of the classifier call."""
    parts = []
    if previous_labels is not None:
        parts.append(f"Previous turn complexity: {previous_labels.complexity.value}.")
    if previous_answer_excerpt:
        excerpt = previous_answer_excerpt[-PREVIOUS_ANSWER_MAX_CHARS:]
        parts.append(f"End of the previous assistant answer:\n<<<\n{excerpt}\n>>>")
    parts.extend(
        [
            f"Attachments present: {'yes' if has_attachments else 'no'}.",
            f"Project context present: {'yes' if has_project_context else 'no'}.",
            f"User message:\n<<<\n{message_text[:MESSAGE_MAX_CHARS]}\n>>>",
        ]
    )
    return "\n\n".join(parts)


async def classify(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    message_text: str,
    previous_labels: RoutingLabels | None,
    previous_answer_excerpt: str | None,
    has_attachments: bool,
    has_project_context: bool,
    *,
    model_hrid: str,
) -> tuple[RoutingLabels, RoutingReason, int]:
    """Rate the complexity of the user's turn.

    Returns `(labels, reason, latency_ms)`. `latency_ms` covers the whole
    classification (agent build and model call); the router timeout bounds the
    model call only. `reason` is `RoutingReason.SHORTCUT` (model call skipped),
    `RoutingReason.CLASSIFIED` or `RoutingReason.FALLBACK` (timeout or error:
    previous labels, else standard with confidence 0).
    """
    word_count = len(message_text.split())
    if previous_labels is not None and not has_attachments and word_count < SHORTCUT_MAX_WORDS:
        logger.debug("Router classifier shortcut (words=%d)", word_count)
        return previous_labels, RoutingReason.SHORTCUT, 0

    user_prompt = build_user_prompt(
        message_text,
        previous_labels,
        previous_answer_excerpt,
        has_attachments,
        has_project_context,
    )

    started = time.perf_counter()
    try:
        # The agent build is kept outside the cancellable window: cancelling a
        # task in the middle of a lazy import leaves modules half-initialised.
        # Only the model call is bounded by the router timeout.
        agent = build_classifier_agent(model_hrid)
        result = await asyncio.wait_for(
            agent.run(user_prompt), timeout=settings.LLM_ROUTER_TIMEOUT_S
        )
        labels = result.output
        reason = RoutingReason.CLASSIFIED
    except TimeoutError:
        labels = previous_labels or FALLBACK_LABELS
        reason = RoutingReason.FALLBACK
        logger.debug(
            "Router classifier timed out after %.0f ms", settings.LLM_ROUTER_TIMEOUT_S * 1000
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        labels = previous_labels or FALLBACK_LABELS
        reason = RoutingReason.FALLBACK
        # The exception type only: model errors may echo the prompt or the output.
        logger.debug("Router classifier failed (%s), falling back", type(exc).__name__)
    latency_ms = int((time.perf_counter() - started) * 1000)

    logger.debug(
        "Router classifier outcome reason=%s complexity=%s confidence=%.2f latency_ms=%d",
        reason.value,
        labels.complexity.value,
        labels.confidence,
        latency_ms,
    )
    return labels, reason, latency_ms
