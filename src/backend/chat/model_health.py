"""Read-only helper for querying cached model health status."""

from django.core.cache import cache


def get_model_health(provider: str, model_id: str) -> str | None:
    """Return 'green', 'yellow', 'red', or None if no data is available yet."""
    return cache.get(f"model_health:{provider}:{model_id}")
