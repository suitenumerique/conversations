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


MAIN_THRESHOLD_CACHE_KEY = "routing_policy:main_eviction_threshold"
FALLBACK_THRESHOLD_CACHE_KEY = "routing_policy:fallback_eviction_threshold"


def _get_threshold(cache_key: str, attr: str) -> str:
    """Read a threshold from cache; on miss, hydrate from the singleton row."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    # Local import: core -> chat would be a startup cycle.
    from core.models import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
        ModelHealthSettings,
    )

    value = getattr(ModelHealthSettings.get_solo(), attr)
    cache.set(cache_key, value, timeout=None)
    return value


def get_main_eviction_threshold() -> str:
    """Cached main-model eviction threshold."""
    return _get_threshold(MAIN_THRESHOLD_CACHE_KEY, "main_eviction_threshold")


def get_fallback_eviction_threshold() -> str:
    """Cached fallback-model eviction threshold (applied to fb1 and fb2)."""
    return _get_threshold(FALLBACK_THRESHOLD_CACHE_KEY, "fallback_eviction_threshold")


def set_main_eviction_threshold(value: str) -> None:
    """Mirror an admin save through to the cache the router reads from."""
    cache.set(MAIN_THRESHOLD_CACHE_KEY, value, timeout=None)


def set_fallback_eviction_threshold(value: str) -> None:
    """Mirror an admin save through to the cache the router reads from."""
    cache.set(FALLBACK_THRESHOLD_CACHE_KEY, value, timeout=None)


def crosses_threshold(status: str | None, threshold: str) -> bool:
    """True when status is at-or-worse-than the given eviction threshold."""
    if status in (None, ModelHealth.Status.GREEN):
        return False
    if threshold == ModelHealth.Status.RED:
        return status == ModelHealth.Status.RED
    return True  # threshold = yellow: any non-green qualifies


def is_fallback_down(hrid: str, status: str | None) -> bool:
    """True if a fallback slot is unavailable: not configured, unknown HRID, or
    health crosses the admin-configured fallback threshold."""
    if not hrid:
        return True
    if settings.LLM_CONFIGURATIONS.get(hrid) is None:
        return True
    return crosses_threshold(status, get_fallback_eviction_threshold())
