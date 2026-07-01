"""Tests for GET /api/v1.0/model-health/."""

from django.core.cache import cache

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.models import ModelHealth

pytestmark = pytest.mark.usefixtures("clear_cache")


@pytest.mark.django_db
def test_model_health_view_unauthenticated(api_client):
    """Unauthenticated requests are rejected."""
    response = api_client.get("/api/v1.0/model-health/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_model_health_view_empty_when_no_data(api_client):
    """Returns empty data list when no records exist yet."""
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1.0/model-health/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"data": []}


@pytest.mark.django_db
def test_model_health_view_returns_latest_per_model(api_client):
    """Returns only the latest status per (provider, model_id) from DB."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    # Create two rows for the same model; only the most recent should appear.
    ModelHealth.objects.create(provider="albert", model_id="BAAI/bge-m3", status="red")
    ModelHealth.objects.create(provider="albert", model_id="BAAI/bge-m3", status="green")
    ModelHealth.objects.create(provider="albert", model_id="mistral-medium", status="red")

    response = api_client.get("/api/v1.0/model-health/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()["data"]
    assert len(data) == 2

    bge = next(d for d in data if d["model_id"] == "BAAI/bge-m3")
    assert bge["status"] == "green"
    assert bge["provider"] == "albert"
    assert "created_at" in bge
    assert "updated_at" in bge

    mistral = next(d for d in data if d["model_id"] == "mistral-medium")
    assert mistral["status"] == "red"


@pytest.mark.django_db
def test_model_health_view_redis_overrides_db_status(api_client):
    """Redis status takes precedence over DB status when present."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    ModelHealth.objects.create(provider="albert", model_id="BAAI/bge-m3", status="red")
    cache.set("model_health:albert:BAAI/bge-m3", "green", timeout=None)

    response = api_client.get("/api/v1.0/model-health/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "green"
