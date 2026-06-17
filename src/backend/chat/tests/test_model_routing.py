"""Tests for resolve_effective_model_hrid()."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument
from unittest.mock import MagicMock, patch

import pytest

from chat.model_routing import resolve_effective_model_hrid


def _make_model(provider_hrid: str, model_name: str):
    model = MagicMock()
    model.provider = MagicMock()
    model.provider.hrid = provider_hrid
    model.model_name = model_name
    return model


@pytest.fixture(name="llm_configs")
def llm_configs_fixture():
    return {
        "main-model": _make_model("albert", "llama3-8b"),
        "fallback-1": _make_model("albert", "mistral-7b"),
        "fallback-2": _make_model("albert", "gpt-mini"),
    }


@pytest.fixture(autouse=True)
def patch_settings(settings, llm_configs):
    settings.LLM_DEFAULT_MODEL_HRID = "main-model"
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    settings.LLM_CONFIGURATIONS = llm_configs


def _patch_health(main=None, fb1=None, fb2=None):
    """Patch get_model_health to return given statuses by model_name."""
    mapping = {
        "llama3-8b": main,
        "mistral-7b": fb1,
        "gpt-mini": fb2,
    }
    return patch(
        "chat.model_health.get_model_health",
        side_effect=lambda provider, model_id: mapping.get(model_id),
    )


def test_main_green_returns_default():
    with _patch_health(main="green"):
        assert resolve_effective_model_hrid(None) == "main-model"


def test_main_unknown_returns_default():
    # Cache miss is treated as healthy: stay on the default model.
    with _patch_health(main=None):
        assert resolve_effective_model_hrid(None) == "main-model"


def test_main_yellow_routes_to_fb1_when_available():
    with _patch_health(main="yellow", fb1="green"):
        assert resolve_effective_model_hrid(None) == "fallback-1"


def test_main_red_routes_to_fb1_when_available():
    with _patch_health(main="red", fb1="green"):
        assert resolve_effective_model_hrid(None) == "fallback-1"


def test_main_yellow_fb1_unknown_still_picks_fb1():
    # Optimistic: fb1 cache miss is not "down".
    with _patch_health(main="yellow", fb1=None):
        assert resolve_effective_model_hrid(None) == "fallback-1"


def test_main_red_fb1_red_routes_to_fb2():
    with _patch_health(main="red", fb1="red", fb2="green"):
        assert resolve_effective_model_hrid(None) == "fallback-2"


def test_main_red_fb1_red_fb2_red_falls_back_to_default(settings):
    with _patch_health(main="red", fb1="red", fb2="red"):
        assert resolve_effective_model_hrid(None) == "main-model"


def test_main_red_no_fallback_configured_returns_default(settings):
    settings.LLM_FALLBACK_MODEL_HRID_1 = ""
    settings.LLM_FALLBACK_MODEL_HRID_2 = ""
    with _patch_health(main="red"):
        assert resolve_effective_model_hrid(None) == "main-model"


def test_main_red_fb1_unknown_hrid_skipped_to_fb2(settings):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "nonexistent-hrid"
    with _patch_health(main="red", fb2="green"):
        assert resolve_effective_model_hrid(None) == "fallback-2"


def test_explicit_non_default_request_passes_through():
    # Dev/staging picker selection always wins, regardless of main health.
    with _patch_health(main="red", fb1="green"):
        assert resolve_effective_model_hrid("fallback-2") == "fallback-2"


def test_explicit_default_request_still_goes_through_cascade():
    # Explicitly asking for the default model is the same as no request: the
    # cascade still runs and routes around an unhealthy main.
    with _patch_health(main="red", fb1="green"):
        assert resolve_effective_model_hrid("main-model") == "fallback-1"


def test_empty_string_request_treated_as_no_request():
    with _patch_health(main="red", fb1="green"):
        assert resolve_effective_model_hrid("") == "fallback-1"
