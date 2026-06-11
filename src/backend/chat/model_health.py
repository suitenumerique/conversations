"""Read/write helpers for the cached model health status."""

from django.core.cache import cache


def model_health_cache_key(provider: str, model_id: str) -> str:
    """Return the cache key holding the live health status for a (provider, model)."""
    return f"model_health:{provider}:{model_id}"


def get_model_health(provider: str, model_id: str) -> str | None:
    """Return 'green', 'yellow', 'red', or None if no data is available yet."""
    return cache.get(model_health_cache_key(provider, model_id))


def set_model_health(provider: str, model_id: str, status: str) -> None:
    """Store the live health status for a (provider, model) with no expiry."""
    cache.set(model_health_cache_key(provider, model_id), status, timeout=None)
