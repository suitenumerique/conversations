"""Structured objects shared by the router classifier and the routing step."""

from pydantic import BaseModel, ConfigDict, Field

from chat.enums import RoutingReason, RoutingTier, TierSource


class RoutingLabels(BaseModel):
    """Output of the classifier: one structured-output call on the router model."""

    model_config = ConfigDict(use_enum_values=False)

    complexity: RoutingTier = Field(
        description="Complexity tier of the user's request: simple, standard or complex."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the complexity label, between 0 and 1.",
    )


class RoutingDecision(BaseModel):
    """Everything the routing step decides for one turn.

    Recorded on the assistant message metadata and announced to the client in a
    ``routing`` data part before the first token.
    """

    tier: RoutingTier
    tier_source: TierSource
    model_hrid: str
    labels: RoutingLabels | None = None
    reason: RoutingReason
    router_confidence: float | None = None
    router_latency_ms: int = 0
    # Model of the previous turn (``conversation.model_hrid`` before this decision
    # was applied), so the stream can tell the user the model changed.
    previous_model_hrid: str | None = None

    @property
    def changed(self) -> bool:
        """Whether this turn runs on a different model than the previous one."""
        return bool(self.previous_model_hrid) and self.previous_model_hrid != self.model_hrid

    def metadata(self) -> dict:
        """Routing keys recorded on the assistant message."""
        return {
            "tier": self.tier.value,
            "tier_source": self.tier_source.value,
            "router_reason": self.reason.value,
            "router_confidence": self.router_confidence,
            "router_latency_ms": self.router_latency_ms,
        }
