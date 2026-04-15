"""Tests for AlbertOpenAI model subclasses and carbon extraction helpers."""
# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

import pytest
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
