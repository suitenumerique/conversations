"""Custom pydantic-ai model subclasses for Albert API providers."""

from typing import Any

from pydantic_ai.models.openai import ChatCompletionChunk, OpenAIChatModel, OpenAIStreamedResponse
from pydantic_ai.providers.openai import OpenAIProvider


def _extract_co2_impact(raw_usage) -> float | None:
    """Extract impact fields from an Albert API usage object.

    Albert returns `impacts` as an extra field (openai SDK uses extra='allow'),
    so it lives in model_extra, not as a direct attribute.
    """
    model_extra = getattr(raw_usage, "model_extra", None) or {}
    raw_impacts = model_extra.get("impacts")
    if not raw_impacts:
        return None

    return raw_impacts.get("kgCO2eq")


def _convert_impact_to_factor_20(impact_kg_co2_eq: float) -> int:
    """Convert a CO2 impact in kg to an integer factor with 20 decimals (for precision).
    This allows us to store the impact as an integer in ModelResponse.details
    while preserving precision.
    Values below 1e-20 would return 0
    """
    return int(impact_kg_co2_eq * 10**20)


class AlbertOpenAIProvider(OpenAIProvider):
    """OpenAIProvider subclass with a distinct name for Albert's OpenAI-compatible API."""

    @property
    def name(self) -> str:
        return "albert_openai"


class AlbertOpenAIStreamedResponse(OpenAIStreamedResponse):
    """Streamed response that preserves Albert's carbon/impacts usage fields."""

    def _map_usage(self, response: ChatCompletionChunk) -> Any:
        """Override to extract Albert's carbon impact data from usage."""
        result = super()._map_usage(response)

        if response.usage:
            co2_impact = _extract_co2_impact(response.usage)
            if co2_impact:
                result.details["co2_impact_factor_20"] = _convert_impact_to_factor_20(co2_impact)
        return result


class AlbertOpenAIChatModel(OpenAIChatModel):
    """
    OpenAIChatModel subclass that preserves Albert's carbon impact data.

    Albert's API returns `impacts` inside `usage` that pydantic-ai normally discards.
    This subclass captures the CO2 value and stores it as an integer (scaled by 10^20
    for precision) in RequestUsage.details["co2_impact_factor_20"], which pydantic-ai
    then accumulates into RunUsage.details across the run.

    Note: Albert sends CO2 data only in the final usage chunk. If this changes and
    partial CO2 values appear in intermediate chunks, RunUsage will sum them, which
    would produce incorrect totals.
    """

    @property
    def _streamed_response_cls(self) -> type[OpenAIStreamedResponse]:
        return AlbertOpenAIStreamedResponse
