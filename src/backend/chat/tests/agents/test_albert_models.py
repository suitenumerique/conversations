"""Tests for AlbertOpenAI model subclasses and carbon extraction helpers."""
# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion
from pydantic_ai.models.openai import OpenAIStreamedResponse
from pydantic_ai.usage import RequestUsage

from chat.providers.albert_models import (
    AlbertOpenAIChatModel,
    AlbertOpenAIProvider,
    AlbertOpenAIStreamedResponse,
    _extract_co2_impact,
)

# ---------------------------------------------------------------------------
# _extract_co2_impact
# ---------------------------------------------------------------------------


def test_extract_carbon_details_returns_empty_extra_when_no_model_extra():
    """Returns None when usage has no model_extra."""
    raw_usage = MagicMock(spec=[])  # no model_extra attribute
    result = _extract_co2_impact(raw_usage)
    assert result is None


def test_extract_co2_impact():
    """Extracts co2 impact field when present in model_extra."""
    kg_co2_eq = 1.5e-9
    kwh = 3.0e-6

    impacts = {"kgCO2eq": kg_co2_eq, "kWh": kwh}
    raw_usage = MagicMock()
    raw_usage.model_extra = {"impacts": impacts}
    result = _extract_co2_impact(raw_usage)
    assert result == pytest.approx(kg_co2_eq)


def test_extract_co2_impact_handles_model_extra_none():
    """Treats model_extra=None the same as missing (returns None)."""
    raw_usage = MagicMock()
    raw_usage.model_extra = None
    result = _extract_co2_impact(raw_usage)
    assert result is None


# ---------------------------------------------------------------------------
# AlbertOpenAIStreamedResponse._map_usage
# ---------------------------------------------------------------------------


@pytest.fixture(name="streamed_response")
def streamed_response_fixture() -> AlbertOpenAIStreamedResponse:
    """Build a minimal AlbertOpenAIStreamedResponse without hitting the network."""
    return AlbertOpenAIStreamedResponse.__new__(AlbertOpenAIStreamedResponse)


def test_map_usage_without_chunk_usage_delegates_to_super(streamed_response):
    """When chunk.usage is None, result is identical to parent's _map_usage output."""
    expected = RequestUsage(input_tokens=10, output_tokens=5)
    chunk = MagicMock()
    chunk.usage = None

    with patch.object(OpenAIStreamedResponse, "_map_usage", return_value=expected) as mock_super:
        result = streamed_response._map_usage(chunk)

    mock_super.assert_called_once_with(chunk)
    assert result is expected
    assert "co2_impact_factor_20" not in result.details


def test_map_usage_without_impacts_does_not_add_co2_detail(streamed_response):
    """When usage has no impacts in model_extra, co2_impact_factor_20 is not added."""
    base_result = RequestUsage(input_tokens=10, output_tokens=5)
    chunk = MagicMock()
    chunk.usage = MagicMock()
    chunk.usage.model_extra = {}  # no impacts

    with patch.object(OpenAIStreamedResponse, "_map_usage", return_value=base_result):
        result = streamed_response._map_usage(chunk)

    assert "co2_impact_factor_20" not in result.details


def test_map_usage_with_impacts_adds_co2_detail(streamed_response):
    """When usage has impacts.kgCO2eq, co2_impact_factor_20 is stored in details."""
    co2_value = 1.23e-9  # kgCO2eq
    impacts = {"kgCO2eq": co2_value, "kWh": 4.5e-6}
    base_result = RequestUsage(input_tokens=10, output_tokens=5)
    chunk = MagicMock()
    chunk.usage = MagicMock()
    chunk.usage.model_extra = {"impacts": impacts}

    with patch.object(OpenAIStreamedResponse, "_map_usage", return_value=base_result):
        result = streamed_response._map_usage(chunk)

    expected_factor = int(co2_value * 10**20)
    assert result.details["co2_impact_factor_20"] == expected_factor


def test_map_usage_with_zero_co2_does_not_add_detail(streamed_response):
    """When impacts.kgCO2eq is 0.0 (falsy), co2_impact_factor_20 is not added."""
    impacts = {"kgCO2eq": 0.0, "kWh": 0.0}
    base_result = RequestUsage(input_tokens=10, output_tokens=5)
    chunk = MagicMock()
    chunk.usage = MagicMock()
    chunk.usage.model_extra = {"impacts": impacts}

    with patch.object(OpenAIStreamedResponse, "_map_usage", return_value=base_result):
        result = streamed_response._map_usage(chunk)

    assert "co2_impact_factor_20" not in result.details


# ---------------------------------------------------------------------------
# AlbertOpenAIChatModel._streamed_response_cls
# ---------------------------------------------------------------------------


def test_albert_chat_model_uses_albert_streamed_response_cls():
    """AlbertOpenAIChatModel._streamed_response_cls returns AlbertOpenAIStreamedResponse."""
    model = AlbertOpenAIChatModel(
        model_name="test-model",
        profile="test-profile",
        provider=AlbertOpenAIProvider(
            base_url="https://test-albert-api.com",
            api_key="test-api-key",
        ),
    )
    assert model._streamed_response_cls is AlbertOpenAIStreamedResponse


# ---------------------------------------------------------------------------
# AlbertOpenAIChatModel._validate_completion
# ---------------------------------------------------------------------------


@pytest.fixture(name="albert_model")
def albert_model_fixture() -> AlbertOpenAIChatModel:
    """Minimal AlbertOpenAIChatModel instance for unit tests."""
    return AlbertOpenAIChatModel(
        model_name="test-model",
        profile=None,
        provider=AlbertOpenAIProvider(
            base_url="https://test-albert-api.com",
            api_key="test-api-key",
        ),
    )


def _make_chat_completion(tool_call_type) -> ChatCompletion:
    """Build a ChatCompletion via model_construct with a tool call of the given type."""
    tool_call = MagicMock()
    tool_call.id = "call_123"
    tool_call.type = tool_call_type
    tool_call.function = MagicMock()
    tool_call.function.name = "final_result"
    tool_call.function.arguments = '{"reason": "ok", "pass": true, "score": 1.0}'

    message = MagicMock()
    message.role = "assistant"
    message.content = None
    message.refusal = None
    message.tool_calls = [tool_call]
    message.model_dump = lambda **_: {
        "role": "assistant",
        "content": None,
        "refusal": None,
        "tool_calls": [
            {
                "id": "call_123",
                "type": tool_call_type,
                "function": {
                    "name": "final_result",
                    "arguments": '{"reason": "ok", "pass": true, "score": 1.0}',
                },
            }
        ],
    }

    choice = MagicMock()
    choice.index = 0
    choice.finish_reason = "tool_calls"
    choice.message = message
    choice.model_dump = lambda **_: {
        "index": 0,
        "finish_reason": "tool_calls",
        "message": message.model_dump(),
    }

    response = MagicMock(spec=ChatCompletion)
    response.id = "chatcmpl-abc"
    response.object = "chat.completion"
    response.created = 1700000000
    response.model = "test-model"
    response.choices = [choice]
    response.usage = None
    response.service_tier = None
    response.model_dump = lambda **_: {
        "id": "chatcmpl-abc",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "test-model",
        "service_tier": None,
        "choices": [choice.model_dump()],
        "usage": None,
    }
    return response


def test_validate_completion_normalizes_none_tool_call_type(albert_model):
    """Tool calls with type=None are normalized to 'function' before validation."""
    response = _make_chat_completion(tool_call_type=None)
    result = albert_model._validate_completion(response)
    tool_call = result.choices[0].message.tool_calls[0]
    assert tool_call.type == "function"
    assert tool_call.function.name == "final_result"


def test_validate_completion_preserves_function_tool_call_type(albert_model):
    """Tool calls already typed as 'function' pass through unchanged."""
    response = _make_chat_completion(tool_call_type="function")
    result = albert_model._validate_completion(response)
    assert result.choices[0].message.tool_calls[0].type == "function"


def _make_malformed_chat_completion(object_value: str, choices_value) -> MagicMock:
    """Build a ChatCompletion mock with non-standard object/choices fields."""
    response = MagicMock(spec=ChatCompletion)
    response.model_dump = lambda **_: {
        "id": "chatcmpl-abc",
        "object": object_value,
        "created": 1700000000,
        "model": "test-model",
        "service_tier": None,
        "choices": choices_value,
        "usage": None,
    }
    return response


def test_validate_completion_normalizes_non_standard_object(albert_model):
    """Non-standard object values are normalized to 'chat.completion'."""
    response = _make_malformed_chat_completion(object_value="list", choices_value=[])
    result = albert_model._validate_completion(response)
    assert result.choices == []


def test_validate_completion_normalizes_null_choices(albert_model):
    """null choices are normalized to an empty list."""
    response = _make_malformed_chat_completion(object_value="chat.completion", choices_value=None)
    result = albert_model._validate_completion(response)
    assert result.choices == []
