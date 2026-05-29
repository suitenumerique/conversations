"""Tests for model_health helper and related settings."""

from unittest.mock import patch

from chat.model_health import get_model_health


def test_albert_health_url_setting_has_default(settings):
    """ALBERT_HEALTH_URL must have a sensible default."""
    assert settings.ALBERT_HEALTH_URL == "https://albert.api.etalab.gouv.fr/health/models"


def test_albert_health_timeout_setting_has_default(settings):
    """ALBERT_HEALTH_TIMEOUT must default to 10."""
    assert settings.ALBERT_HEALTH_TIMEOUT == 10


def test_get_model_health_returns_cached_status():
    """Returns the status string when the Redis key exists."""
    with patch("chat.model_health.cache") as mock_cache:
        mock_cache.get.return_value = "green"
        result = get_model_health("albert", "BAAI/bge-m3")
        assert result == "green"
        mock_cache.get.assert_called_once_with("model_health:albert:BAAI/bge-m3")


def test_get_model_health_returns_none_on_cache_miss():
    """Returns None when the Redis key is absent."""
    with patch("chat.model_health.cache") as mock_cache:
        mock_cache.get.return_value = None
        result = get_model_health("albert", "unknown-model")
        assert result is None
