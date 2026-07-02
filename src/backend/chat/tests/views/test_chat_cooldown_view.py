"""Tests for GET /api/v1.0/chat-cooldown/."""

import pytest
from freezegun import freeze_time
from rest_framework import status

from core.factories import UserFactory

from chat.rate_limiting import set_cooldown

pytestmark = pytest.mark.usefixtures("clear_cache")


@pytest.mark.django_db
def test_chat_cooldown_view_unauthenticated(api_client):
    """Unauthenticated requests are rejected."""
    response = api_client.get("/api/v1.0/chat-cooldown/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_chat_cooldown_view_zero_when_no_cooldown(api_client):
    """Returns 0 when the user has no active cooldown."""
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1.0/chat-cooldown/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"cooldown_seconds": 0}


@pytest.mark.django_db
def test_chat_cooldown_view_returns_remaining_for_current_user(api_client):
    """Returns the remaining seconds of the authenticated user's cooldown."""
    user = UserFactory()
    api_client.force_authenticate(user=user)
    with freeze_time("2026-06-09T10:00:00Z"):
        set_cooldown(user.pk, 60)
        response = api_client.get("/api/v1.0/chat-cooldown/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"cooldown_seconds": 60}


@pytest.mark.django_db
def test_chat_cooldown_view_is_per_user(api_client):
    """One user's cooldown does not leak into another user's response."""
    user = UserFactory()
    other = UserFactory()
    api_client.force_authenticate(user=user)
    with freeze_time("2026-06-09T10:00:00Z"):
        set_cooldown(other.pk, 60)
        response = api_client.get("/api/v1.0/chat-cooldown/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"cooldown_seconds": 0}
