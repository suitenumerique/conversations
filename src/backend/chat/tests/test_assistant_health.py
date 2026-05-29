"""Tests for compute_assistant_health_banners() helper."""

from unittest.mock import MagicMock, patch

import pytest

from chat.assistant_health import compute_assistant_health_banners


def _make_model(provider_hrid: str, model_name: str):
    """Return a minimal LLModel-like mock."""
    model = MagicMock()
    model.provider = MagicMock()
    model.provider.hrid = provider_hrid
    model.model_name = model_name
    return model


@pytest.fixture()
def llm_configs():
    return {
        "main-model": _make_model("albert", "llama3-8b"),
        "fallback-1": _make_model("albert", "mistral-7b"),
        "fallback-2": _make_model("albert", "gpt-mini"),
    }


@pytest.fixture(autouse=True)
def patch_settings(settings, llm_configs):
    settings.LLM_DEFAULT_MODEL_HRID = "main-model"
    settings.LLM_FALLBACK_MODEL_HRID_1 = ""
    settings.LLM_FALLBACK_MODEL_HRID_2 = ""
    settings.LLM_CONFIGURATIONS = llm_configs


def _patch_health(main=None, fb1=None, fb2=None):
    """Patch get_model_health to return given statuses by model_name."""
    mapping = {
        "llama3-8b": main,
        "mistral-7b": fb1,
        "gpt-mini": fb2,
    }
    return patch(
        "chat.assistant_health.get_model_health",
        side_effect=lambda provider, model_id: mapping.get(model_id),
    )


# --- main green/None --------------------------------------------------------

def test_main_green_no_banner(settings):
    with _patch_health(main="green"):
        result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


def test_main_none_no_banner(settings):
    with _patch_health(main=None):
        result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


# --- main orange ------------------------------------------------------------

def test_main_orange_fb_green_no_banner(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="orange", fb1="green"):
        result = compute_assistant_health_banners()
    assert result["banners"] == []
    assert result["blocked"] is False


def test_main_orange_fb_orange_slow_warning(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="orange", fb1="orange"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "lentement" in result["banners"][0]["title"]
    assert result["blocked"] is False


def test_main_orange_no_fallback_slow_warning(settings):
    # No fallbacks configured → fb_effective = "red"
    with _patch_health(main="orange"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "lentement" in result["banners"][0]["title"]
    assert result["blocked"] is False


# --- main red ---------------------------------------------------------------

def test_main_red_fb_green_no_banner(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="red", fb1="green"):
        result = compute_assistant_health_banners()
    assert result["banners"] == []
    assert result["blocked"] is False


def test_main_red_fb_orange_degraded_warning(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="red", fb1="orange"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "dégradé" in result["banners"][0]["title"]
    assert result["blocked"] is False


def test_main_red_fb_red_blocked(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="red", fb1="red"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "alert"
    assert "indisponible" in result["banners"][0]["title"].lower()
    assert result["blocked"] is True


def test_main_red_no_fallback_blocked(settings):
    # No fallbacks configured → fb_effective = "red" → blocked
    with _patch_health(main="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is True


# --- fallback chain precedence ----------------------------------------------

def test_fb_chain_first_non_red_wins(settings, llm_configs):
    # fb1 is red, fb2 is orange → fb_effective should be orange
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb1="red", fb2="orange"):
        result = compute_assistant_health_banners()
    assert result["banners"][0]["level"] == "warning"
    assert "dégradé" in result["banners"][0]["title"]
    assert result["blocked"] is False


def test_fb_chain_both_red_blocked(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb1="red", fb2="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is True


# --- unknown HRID -----------------------------------------------------------

def test_unknown_main_hrid_treated_as_no_data(settings):
    settings.LLM_DEFAULT_MODEL_HRID = "nonexistent-hrid"
    result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


# --- banner content is empty string -----------------------------------------

def test_banner_content_is_empty_string(settings):
    with _patch_health(main="red"):
        result = compute_assistant_health_banners()
    assert result["banners"][0]["content"] == ""
