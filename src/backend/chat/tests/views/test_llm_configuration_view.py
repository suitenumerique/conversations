"""Tests for the LLM configuration view."""

import pytest
from rest_framework import status

from core.factories import UserFactory
from core.feature_flags.flags import FeatureFlags, FeatureToggle

from chat.llm_configuration import LLModel, LLMProvider
from chat.models import RoutingTierSettings


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
                "is_active": True,
                "is_default": True,
                "model_name": "amazing-llm",
                "supports_image": False,
            },
            {
                "hrid": "model-2",
                "human_readable_name": "Another LLM",
                "icon": "",
                "is_active": True,
                "is_default": False,
                "model_name": "another-llm",
                "supports_image": False,
            },
        ]
    }


@pytest.mark.django_db
def test_llm_configuration_view_hides_utility_models(api_client, llm_configurations, settings):  # pylint: disable=unused-argument
    """With the router on, utility models are not offered as a conversation model."""
    settings.FEATURE_FLAGS = FeatureFlags(router=FeatureToggle.ENABLED)
    settings.LLM_CONFIGURATIONS["model-2"].role = "utility"
    api_client.force_authenticate(user=UserFactory())
    response = api_client.get("/api/v1.0/llm-configuration/")

    assert [model["hrid"] for model in response.json()["models"]] == ["model-1"]


@pytest.mark.django_db
def test_llm_configuration_view_lists_utility_models_with_the_router_off(
    api_client,
    llm_configurations,  # pylint: disable=unused-argument
    settings,
):
    """With the router off the model list is the upstream one, utility models included."""
    settings.FEATURE_FLAGS = FeatureFlags(router=FeatureToggle.DISABLED)
    settings.LLM_CONFIGURATIONS["model-2"].role = "utility"
    api_client.force_authenticate(user=UserFactory())
    response = api_client.get("/api/v1.0/llm-configuration/")

    assert [model["hrid"] for model in response.json()["models"]] == ["model-1", "model-2"]


@pytest.mark.django_db
def test_llm_configuration_view_lists_tiers_with_the_router_on(
    api_client,
    llm_configurations,  # pylint: disable=unused-argument
    settings,
):
    """Auto first, then each tier whose model is active, with its leaves and no model name."""
    settings.FEATURE_FLAGS = FeatureFlags(router=FeatureToggle.ENABLED)
    settings.LLM_CONFIGURATIONS["model-2"].is_active = False
    tier_settings = RoutingTierSettings.get_solo()
    tier_settings.simple_model_hrid = "model-1"
    tier_settings.standard_model_hrid = "model-2"  # inactive: the tier is omitted
    tier_settings.complex_model_hrid = ""  # blank: the default model
    tier_settings.save()

    api_client.force_authenticate(user=UserFactory())
    response = api_client.get("/api/v1.0/llm-configuration/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["tiers"] == [
        {"slug": "auto", "label_key": "router.tier.auto", "recommended": True},
        {"slug": "simple", "label_key": "router.tier.simple", "leaves": 1},
        {"slug": "complex", "label_key": "router.tier.complex", "leaves": 3},
    ]


@pytest.mark.django_db
def test_llm_configuration_view_has_no_tiers_with_the_router_off(
    api_client,
    llm_configurations,  # pylint: disable=unused-argument
    settings,
):
    """With the router off the payload is unchanged."""
    settings.FEATURE_FLAGS = FeatureFlags(router=FeatureToggle.DISABLED)
    api_client.force_authenticate(user=UserFactory())
    response = api_client.get("/api/v1.0/llm-configuration/")

    assert "tiers" not in response.json()
