"""Unit tests for the PostHog events reported by the user viewset."""

from unittest.mock import patch

import pytest

from core.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(name="posthog_configured", autouse=True)
def posthog_configured_fixture(settings):
    """Configure PostHog so the capture guard lets the events through."""
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}


@pytest.fixture(autouse=True)
def _connectors_offered(settings):
    """Offer data.gouv and one declared connector."""
    settings.DATAGOUV_CONNECTOR_URL = "https://mcp.data.gouv.fr/mcp"
    settings.MCP_CONNECTORS = [
        {"slug": "legi", "name": "Légifrance", "url": "https://l/mcp", "instructions": "Law."}
    ]


def _patch_user(api_client, user, payload):
    """PATCH the given user as themselves, with PostHog stubbed out."""
    api_client.force_login(user)

    with patch("core.analytics.posthog") as mock_posthog:
        response = api_client.patch(
            f"/api/v1.0/users/{user.pk!s}/",
            payload,
            format="json",
        )

    assert response.status_code == 200
    return mock_posthog


def test_enabling_the_datagouv_connector_is_captured(api_client):
    """Opting into the connector reports it as enabled."""
    user = UserFactory(allowed_connectors=[])

    mock_posthog = _patch_user(api_client, user, {"allowed_connectors": ["datagouv"]})

    mock_posthog.capture.assert_called_once()
    call = mock_posthog.capture.call_args
    assert call.args[0] == "connector_toggled"
    assert call.kwargs["distinct_id"] == str(user.pk)
    assert call.kwargs["properties"] == {"connector_id": "datagouv", "enabled": True}


def test_disabling_the_datagouv_connector_is_captured(api_client):
    """Opting back out reports it as disabled, so abandonment is measurable."""
    user = UserFactory(allowed_connectors=["datagouv"])

    mock_posthog = _patch_user(api_client, user, {"allowed_connectors": []})

    mock_posthog.capture.assert_called_once()
    call = mock_posthog.capture.call_args
    assert call.args[0] == "connector_toggled"
    assert call.kwargs["properties"] == {"connector_id": "datagouv", "enabled": False}


def test_resending_the_same_value_is_not_captured(api_client):
    """A save that changes nothing is not a toggle."""
    user = UserFactory(allowed_connectors=["datagouv"])

    mock_posthog = _patch_user(api_client, user, {"allowed_connectors": ["datagouv"]})

    mock_posthog.capture.assert_not_called()


def test_updating_another_setting_is_not_captured(api_client):
    """Only the connector opt-in reports a connector event."""
    user = UserFactory(allow_smart_web_search=False)

    mock_posthog = _patch_user(api_client, user, {"allow_smart_web_search": True})

    mock_posthog.capture.assert_not_called()


def test_each_changed_connector_is_captured(api_client):
    """Swapping one connector for another reports both, each with its own state."""
    user = UserFactory(allowed_connectors=["datagouv"])

    mock_posthog = _patch_user(api_client, user, {"allowed_connectors": ["legi"]})

    assert [call.kwargs["properties"] for call in mock_posthog.capture.call_args_list] == [
        {"connector_id": "datagouv", "enabled": False},
        {"connector_id": "legi", "enabled": True},
    ]
