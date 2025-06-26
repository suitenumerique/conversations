"""Common test fixtures for chat application tests."""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Fixture to provide an API client for testing."""
    return APIClient()
