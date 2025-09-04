"""Tests for the LLM configuration view."""

import pytest
from rest_framework import status

from core.factories import UserFactory

from chat.llm_configuration import LLModel, LLMProvider


@pytest.fixture(name="llm_configurations")
def llm_configurations_fixture(settings):
    """Fixture to set up LLM configurations in settings."""
    settings.LLM_CONFIGURATIONS = {
        "model-1": LLModel(
            hrid="model-1",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon="base64encodediconstring",
            system_prompt="You are an amazing assistant.",
            tools=["web-search", "calculator"],
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
        "model-2": LLModel(
            hrid="model-2",
            model_name="another-llm",
            human_readable_name="Another LLM",
            is_active=True,
            icon="",
            system_prompt="You are another assistant.",
            tools=[],
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "model-1"


@pytest.mark.django_db
def test_llm_configuration_view_unauthenticated(api_client):
    """Test that unauthenticated access is denied."""
    response = api_client.get("/api/v1.0/llm-configuration/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_llm_configuration_view_authenticated(api_client, llm_configurations):  # pylint: disable=unused-argument
    """Test that authenticated access returns the correct LLM configurations."""
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1.0/llm-configuration/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "models": [
            {
                "hrid": "model-1",
                "human_readable_name": "Amazing LLM",
                "icon": "base64encodediconstring",
                "is_default": True,
                "model_name": "amazing-llm",
            },
            {
                "hrid": "model-2",
                "human_readable_name": "Another LLM",
                "icon": "",
                "is_default": False,
                "model_name": "another-llm",
            },
        ]
    }
