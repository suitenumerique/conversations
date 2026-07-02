"""Tests for GET /api/v1.0/assistant-health/."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument
from unittest.mock import MagicMock

from django.core.cache import cache
from django.urls import reverse

import pytest

from core.factories import UserFactory

MAIN_KEY = "model_health:albert:llama3-8b"
FB1_KEY = "model_health:albert:mistral-7b"


def _make_model(model_name: str):
    model = MagicMock()
    model.provider = MagicMock()
    model.provider.hrid = "albert"
    model.model_name = model_name
    return model


@pytest.fixture()
def authenticated_client(client, db):
    user = UserFactory()
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def patch_llm_settings(settings):
    settings.LLM_DEFAULT_MODEL_HRID = "main-model"
    settings.LLM_CONFIGURATIONS = {
        "main-model": _make_model("llama3-8b"),
        "fallback-1": _make_model("mistral-7b"),
    }


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_assistant_health_requires_auth(client):
    response = client.get(reverse("assistant-health"))
    assert response.status_code == 401


@pytest.mark.django_db
def test_assistant_health_no_banners(authenticated_client):
    cache.set(MAIN_KEY, "green")
    response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert data["banners"] == []
    assert data["blocked"] is False


@pytest.mark.django_db
def test_assistant_health_with_warning_banner(authenticated_client, settings):
    settings.LLM_FALLBACK_MODEL_HRID_1 = "fallback-1"
    cache.set(MAIN_KEY, "yellow")
    cache.set(FB1_KEY, "green")
    response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["banners"]) == 1
    assert data["banners"][0]["level"] == "warning"
    assert data["blocked"] is False


@pytest.mark.django_db
def test_assistant_health_blocked(authenticated_client):
    # main=red, no fallbacks configured → all_down=True, SiteConfiguration default=True
    cache.set(MAIN_KEY, "red")
    response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert data["blocked"] is True
    assert data["banners"][0]["level"] == "alert"


@pytest.mark.django_db
def test_assistant_health_only_get_allowed(authenticated_client):
    response = authenticated_client.post(reverse("assistant-health"))
    assert response.status_code == 405


@pytest.mark.django_db
def test_assistant_health_response_schema(authenticated_client, settings):
    # Unknown HRID → get_status_for_hrid returns None → no banners, no cache needed
    settings.LLM_DEFAULT_MODEL_HRID = "nonexistent"
    settings.LLM_CONFIGURATIONS = {}
    response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["banners"], list)
    assert isinstance(data["blocked"], bool)
    assert set(data.keys()) == {"banners", "blocked"}
