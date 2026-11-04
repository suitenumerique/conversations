"""Tokens and CO2 a turn cost, and how they add up on the conversation."""

import dataclasses

from pydantic_ai import RunUsage

from chat.vercel_ai_sdk.core import events_v4

# Albert reports the CO2 impact as an integer scaled by 10^20.
_CO2_IMPACT_SCALE = 10**20


def _extract_co2_from_usage(usage: RunUsage) -> float:
    """Extract the CO2 impact from a RunUsage object.

    Reads `co2_impact_factor_20` from usage.details (set by AlbertOpenAIStreamedResponse),
    reverting the 10^20 integer scaling back to a float in kgCO2eq.
    Non-Albert providers always return 0 (details key absent).
    """
    if usage_details := usage.details:
        return usage_details.get("co2_impact_factor_20", 0) / _CO2_IMPACT_SCALE
    return 0


@dataclasses.dataclass(frozen=True)
class AgentUsage:
    """Tokens and CO2 (kgCO2eq): one turn's, or a conversation's running total.

    The total is stored on `ChatConversation.agent_usage` in the camelCase form
    the AI SDK uses (`to_stored` / `from_stored`).
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    co2_impact: float = 0

    @classmethod
    def from_run(cls, usage: RunUsage) -> "AgentUsage":
        """What a finished pydantic-ai run cost, across all its model requests."""
        return cls(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            co2_impact=_extract_co2_from_usage(usage),
        )

    @classmethod
    def from_stored(cls, agent_usage: dict) -> "AgentUsage":
        """Read `ChatConversation.agent_usage`, empty until the first turn lands."""
        return cls(
            prompt_tokens=agent_usage.get("promptTokens", 0),
            completion_tokens=agent_usage.get("completionTokens", 0),
            co2_impact=agent_usage.get("co2_impact", 0),
        )

    def to_stored(self) -> dict:
        """The form `ChatConversation.agent_usage` holds."""
        return {
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "co2_impact": self.co2_impact,
        }

    def to_event(self) -> events_v4.Usage:
        """The usage a v4 finish frame carries."""
        return events_v4.Usage(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            co2_impact=self.co2_impact,
        )

    def __add__(self, other: "AgentUsage") -> "AgentUsage":
        return AgentUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            co2_impact=self.co2_impact + other.co2_impact,
        )
