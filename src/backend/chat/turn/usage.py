"""Tokens and CO2 a turn cost, and how they add up on the conversation."""

import dataclasses

from asgiref.sync import sync_to_async
from pydantic_ai import RunUsage

from chat.llm_configuration import LLModel
from chat.rate_limiting import record_and_compute_cooldown
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


class TokenMeter:
    """Charges a turn's tokens to the user's cooldown window, as they are spent.

    One per turn: it remembers what it has charged, so each call only adds the
    tokens spent since the last one.
    """

    def __init__(self, user_pk, model_configuration: LLModel):
        self._user_pk = user_pk
        self._model_configuration = model_configuration
        self._recorded = 0

    async def charge_run(self, run) -> int:
        """Charge what `run` has spent through the model so far."""
        usage = run.usage
        return await self.charge(int(usage.input_tokens) + int(usage.output_tokens))

    async def charge(self, total_tokens: int) -> int:
        """Charge the tokens this turn has spent since the last call.

        Recorded as it goes, because a turn that never reaches the end spent
        its tokens all the same. The window adds up, so the increments total
        what one final call would have charged.
        """
        unrecorded = total_tokens - self._recorded
        if unrecorded <= 0:
            return 0
        self._recorded = total_tokens
        return await sync_to_async(record_and_compute_cooldown)(
            self._user_pk, self._model_configuration, unrecorded
        )
