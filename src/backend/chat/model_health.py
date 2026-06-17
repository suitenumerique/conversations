"""Read/write helpers for the cached model health status."""

from django.conf import settings
from django.core.cache import cache

from chat.models import ModelHealth


def model_health_cache_key(provider: str, model_id: str) -> str:
    """Return the cache key holding the live health status for a (provider, model)."""
    return f"model_health:{provider}:{model_id}"


def get_model_health(provider: str, model_id: str) -> str | None:
    """Return 'green', 'yellow', 'red', or None if no data is available yet."""
    return cache.get(model_health_cache_key(provider, model_id))


def set_model_health(provider: str, model_id: str, status: str) -> None:
    """Store the live health status for a (provider, model) with no expiry."""
    cache.set(model_health_cache_key(provider, model_id), status, timeout=None)


def get_status_for_hrid(hrid: str) -> str | None:
    """Return cached health status for an HRID, or None if unknown/uncached."""
    if not hrid:
        return None
    model = settings.LLM_CONFIGURATIONS.get(hrid)
    if model is None:
        return None
    if model.provider:
        return get_model_health(model.provider.hrid, model.model_name)
    # model_name in "provider:model_id" format when no explicit provider is configured
    parts = model.model_name.split(":", 1)
    if len(parts) == 2:
        return get_model_health(parts[0], parts[1])
    return None


def is_fallback_down(hrid: str, status: str | None) -> bool:
    """True if a fallback slot is unavailable: not configured, unknown HRID, or explicitly red."""
    if not hrid:
        return True
    if settings.LLM_CONFIGURATIONS.get(hrid) is None:
        return True
    return status == ModelHealth.Status.RED
