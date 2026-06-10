"""Fixtures for tests in the conversations core application"""

from django.core.cache import cache

import pytest


@pytest.fixture(autouse=True)
def clear_cache():
    """Fixture to clear the cache before and after each test."""
    cache.clear()
    yield
    cache.clear()
