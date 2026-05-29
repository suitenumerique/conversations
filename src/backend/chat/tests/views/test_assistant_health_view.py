"""Tests for GET /api/v1.0/assistant-health/."""

from unittest.mock import patch

from django.urls import reverse

import pytest

from core.factories import UserFactory


@pytest.fixture()
def authenticated_client(client, db):
    user = UserFactory()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_assistant_health_requires_auth(client):
    url = reverse("assistant-health")
    response = client.get(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_assistant_health_no_banners(authenticated_client):
    with patch(
        "chat.views.compute_assistant_health_banners",
        return_value={"banners": [], "blocked": False},
    ):
        response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert data == {"banners": [], "blocked": False}


@pytest.mark.django_db
def test_assistant_health_with_warning_banner(authenticated_client):
    with patch(
        "chat.views.compute_assistant_health_banners",
        return_value={
            "banners": [
                {"level": "warning", "title": "L'assistant répond lentement", "content": ""}
            ],
            "blocked": False,
        },
    ):
        response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["banners"]) == 1
    assert data["banners"][0]["level"] == "warning"
    assert data["blocked"] is False


@pytest.mark.django_db
def test_assistant_health_blocked(authenticated_client):
    with patch(
        "chat.views.compute_assistant_health_banners",
        return_value={
            "banners": [
                {"level": "alert", "title": "Assistant indisponible", "content": ""}
            ],
            "blocked": True,
        },
    ):
        response = authenticated_client.get(reverse("assistant-health"))
    assert response.status_code == 200
    data = response.json()
    assert data["blocked"] is True
    assert data["banners"][0]["level"] == "alert"
