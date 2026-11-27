"""Unit tests for the PostHog events reported by the user viewset."""

from unittest.mock import patch

import pytest

from core.factories import UserFactory
from core.feature_flags.flags import FeatureToggle

from chat.tests.connectors.declarations import datagouv_declaration, sofia_declaration

pytestmark = pytest.mark.django_db


@pytest.fixture(name="declared", autouse=True)
def declared_fixture(settings, feature_flags):
    """The deployment offers data.gouv to its cohort, and SofIA."""
    feature_flags.datagouv_connector = FeatureToggle.ENABLED
    settings.MCP_CONNECTORS = [datagouv_declaration(), sofia_declaration()]


@pytest.fixture(name="posthog_configured", autouse=True)
def posthog_configured_fixture(settings):
    """Configure PostHog so the capture guard lets the events through."""
    settings.POSTHOG_KEY = {"id": "key", "host": "https://posthog.test"}


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


def test_each_connector_changed_in_one_save_is_captured(api_client):
    """One event per connector switched, named by its slug."""
    user = UserFactory(allowed_connectors=["datagouv"])

    mock_posthog = _patch_user(api_client, user, {"allowed_connectors": ["sofia"]})

    assert sorted(
        (
            call.args[0],
            call.kwargs["properties"]["connector_id"],
            call.kwargs["properties"]["enabled"],
        )
        for call in mock_posthog.capture.call_args_list
    ) == [("connector_toggled", "datagouv", False), ("connector_toggled", "sofia", True)]


def test_reordering_the_opt_ins_is_not_captured(api_client):
    """The same connectors in another order switch nothing."""
    user = UserFactory(allowed_connectors=["datagouv", "sofia"])

    mock_posthog = _patch_user(api_client, user, {"allowed_connectors": ["sofia", "datagouv"]})

    mock_posthog.capture.assert_not_called()
