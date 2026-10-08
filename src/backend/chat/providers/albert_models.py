"""Custom pydantic-ai model subclasses for Albert API providers."""

import logging
from typing import Any

from openai.types import chat
from pydantic_ai.models.openai import (
    ChatCompletionChunk,
    OpenAIChatModel,
    OpenAIStreamedResponse,
    _ChatCompletion,
)
from pydantic_ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


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


def content_parts_to_text(parts: list) -> str | None:
    """Join a list of content parts (str or {"text": ...} dicts) into one string.

    Albert sometimes returns message content as a list of parts instead of a
    string, e.g. with citation/reference parts alongside the text. Non-text parts
    are dropped; None when no text is left.
    """
    text_parts = []
    for part in parts:
        if isinstance(part, str):
            text_parts.append(part)
        elif isinstance(part, dict):
            text_parts.append(part.get("text") or "")
        else:
            logger.info("Unexpected content part type: %s", type(part))
    return "".join(text_parts) or None


def _join_list_content(choices: list) -> None:
    """Replace list-shaped message content with its joined text, in place."""
    for choice in choices:
        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), list):
            message["content"] = content_parts_to_text(message["content"])


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


def _normalize_tool_call_types(choices: list) -> None:
    """Coerce non-conforming tool_call `type` values to 'function' in place.

    'custom' is only valid with a `custom` payload; any other type (including
    'custom' with a function payload) must be 'function' to pass the openai SDK
    union validation.
    """
    for choice in choices:
        for tool_call in (choice.get("message") or {}).get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            is_custom = tool_call.get("type") == "custom" and "custom" in tool_call
            if not is_custom and tool_call.get("type") != "function":
                tool_call["type"] = "function"


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

    def _validate_completion(self, response: chat.ChatCompletion) -> _ChatCompletion:
        """Normalize Albert API quirks before validation.

        Albert's OpenAI-compatible API has two known non-conformances:
        1. tool_calls[].type may not be 'function' — normalized to 'function',
           unless the tool call is a genuine custom tool call (type='custom'
           with a `custom` payload, which the openai SDK requires).
        2. On multi-turn tool-call conversations, the second response sometimes
           returns a non-standard `object` value. This is normalized before
           passing to _ChatCompletion.model_validate().
        3. message.content may be a list of text parts — joined into a string.
           warnings=False: the openai SDK types content as str and would warn on
           dumping the list.
        """
        data = response.model_dump(warnings=False)

        if data.get("object") != "chat.completion":
            data["object"] = "chat.completion"

        # Only normalize tool-call types when `choices` is a genuine list. A
        # malformed non-list value is left untouched so model_validate() raises a
        # clear ValidationError here, rather than being coerced to `[]` (which
        # passes validation and then makes pydantic-ai raise IndexError on
        # response.choices[0]).
        choices = data.get("choices")
        if isinstance(choices, list):
            _normalize_tool_call_types(choices)
            _join_list_content(choices)

        return _ChatCompletion.model_validate(data)
