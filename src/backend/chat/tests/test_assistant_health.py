"""Tests for compute_assistant_health_banners() helper."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument
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
    settings.LLM_CONFIGURATIONS = llm_configs


@pytest.fixture(autouse=True)
def patch_site_config():
    """Provide a default SiteConfiguration without hitting the database."""
    mock_config = MagicMock()
    mock_config.block_on_full_outage = True
    with patch("chat.assistant_health.SiteConfiguration.get_solo", return_value=mock_config):
        yield mock_config


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


# --- main green/None --------------------------------------------------------


def test_main_green_no_banner(settings):
    with _patch_health(main="green"):
        result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


def test_main_none_no_banner(settings):
    with _patch_health(main=None):
        result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


# --- main yellow/red + fb1=green → slow banner ------------------------------


def test_main_yellow_fb1_green_slow_banner(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="yellow", fb1="green"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "slowdowns" in result["banners"][0]["title"]
    assert result["blocked"] is False


def test_main_red_fb1_green_slow_banner(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="red", fb1="green"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "slowdowns" in result["banners"][0]["title"]
    assert result["blocked"] is False


# --- main yellow → degraded (never blocked) ---------------------------------


@pytest.mark.django_db
def test_main_yellow_fb_yellow_degraded(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="yellow", fb1="yellow"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


def test_main_yellow_no_fallback_degraded(settings):
    # No fallbacks configured → all_down=True, but main=yellow (not red) → degraded, not blocked.
    with _patch_health(main="yellow"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


@pytest.mark.django_db
def test_main_yellow_fb1_none_degraded(settings, llm_configs):
    # Cache miss (None) on fb1 is optimistic: not down → degraded.
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="yellow", fb1=None):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


# --- main red → degraded ----------------------------------------------------


@pytest.mark.django_db
def test_main_red_fb_yellow_degraded(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="red", fb1="yellow"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


@pytest.mark.django_db
def test_main_red_fb1_red_fb2_green_degraded(settings, llm_configs):
    # fb2=green does NOT trigger slow banner — only fb1=green does.
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb1="red", fb2="green"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


@pytest.mark.django_db
def test_main_red_fb1_red_fb2_yellow_degraded(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb1="red", fb2="yellow"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


@pytest.mark.django_db
def test_main_red_fb1_none_degraded(settings, llm_configs):
    # Cache miss (None) on fb1 is optimistic: not down → degraded, not blocked.
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb1=None, fb2="green"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


# --- main red + all fallbacks down → unavailable (blocked) ------------------


@pytest.mark.django_db
def test_main_red_fb1_red_unavailable(settings, llm_configs):
    # fb1=red, fb2="" (not configured) → all_down=True → unavailable.
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    with _patch_health(main="red", fb1="red"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "alert"
    assert "unavailable" in result["banners"][0]["title"].lower()
    assert result["blocked"] is True


def test_main_red_no_fallback_unavailable(settings):
    # No fallbacks configured → all_down=True → unavailable.
    with _patch_health(main="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is True
    assert result["banners"][0]["level"] == "alert"


def test_main_red_no_fallback_degraded_when_block_disabled(settings, patch_site_config):
    # Admin disabled blocking → degraded banner (warning), not unavailable (alert).
    patch_site_config.block_on_full_outage = False
    with _patch_health(main="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is False
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"].lower()


@pytest.mark.django_db
def test_main_red_both_fallbacks_red_unavailable(settings, llm_configs):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb1="red", fb2="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is True
    assert result["banners"][0]["level"] == "alert"


def test_main_red_fb1_unknown_hrid_unavailable(settings):
    # HRID is set but not in LLM_CONFIGURATIONS → treated as down, not a cache miss.
    settings.LLM_FALLBACK_MODEL_HRID_1 = "nonexistent-hrid"
    with _patch_health(main="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is True


@pytest.mark.django_db
def test_main_red_fb1_empty_fb2_red_unavailable(settings, llm_configs):
    # fb1="" (not configured → down) + fb2=red (down) → all_down=True → unavailable.
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb2="red"):
        result = compute_assistant_health_banners()
    assert result["blocked"] is True


# --- fallback partially configured ------------------------------------------


@pytest.mark.django_db
def test_fb1_empty_fb2_yellow_degraded(settings, llm_configs):
    # fb1="" (down) but fb2=yellow (not down) → all_down=False → degraded.
    settings.LLM_FALLBACK_MODEL_HRID_2 = "fallback-2"
    with _patch_health(main="red", fb2="yellow"):
        result = compute_assistant_health_banners()
    assert len(result["banners"]) == 1
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


# --- unknown / empty HRID ---------------------------------------------------


def test_unknown_main_hrid_treated_as_no_data(settings):
    settings.LLM_DEFAULT_MODEL_HRID = "nonexistent-hrid"
    result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


def test_empty_default_model_hrid(settings):
    settings.LLM_DEFAULT_MODEL_HRID = ""
    result = compute_assistant_health_banners()
    assert result == {"banners": [], "blocked": False}


# --- provider parsing (no explicit provider) ---------------------------------


def test_main_hrid_with_no_explicit_provider(settings):
    # When model.provider is None, model_name is split on ":" to derive (provider, model_id).
    model = MagicMock()
    model.provider = None
    model.model_name = "openai:gpt-4o"
    settings.LLM_DEFAULT_MODEL_HRID = "no-provider-model"
    settings.LLM_CONFIGURATIONS = {"no-provider-model": model}

    with patch("chat.model_health.get_model_health", return_value="yellow") as mock_health:
        result = compute_assistant_health_banners()

    mock_health.assert_called_once_with("openai", "gpt-4o")
    # main=yellow, no fallbacks → all_down=True (both empty), but main≠red → degraded, not blocked.
    assert result["banners"][0]["level"] == "warning"
    assert "degraded" in result["banners"][0]["title"]
    assert result["blocked"] is False


def test_main_hrid_with_no_explicit_provider_no_colon(settings):
    # When model.provider is None and model_name has no ":", _get_status_for_hrid returns None.
    model = MagicMock()
    model.provider = None
    model.model_name = "gpt4o-without-colon"
    settings.LLM_DEFAULT_MODEL_HRID = "no-provider-model"
    settings.LLM_CONFIGURATIONS = {"no-provider-model": model}

    with patch("chat.model_health.get_model_health") as mock_health:
        result = compute_assistant_health_banners()

    mock_health.assert_not_called()
    assert result == {"banners": [], "blocked": False}
