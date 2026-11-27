"""/config/ lists the connectors the deployment offers, so the UI needs no release per connector."""

import pytest
from rest_framework.test import APIClient

from chat.tests.connectors.declarations import datagouv_declaration, sofia_declaration

pytestmark = pytest.mark.django_db


def _connectors():
    response = APIClient().get("/api/v1.0/config/")
    assert response.status_code == 200
    return response.json()["connectors"]


def test_no_connector_declared_lists_none(settings):
    """Nothing declared, nothing to show."""
    settings.MCP_CONNECTORS = []

    assert _connectors() == []


def test_each_declared_connector_is_listed_in_order(settings):
    """What the UI needs to show it, and nothing it does not."""
    settings.MCP_CONNECTORS = [
        datagouv_declaration(),
        sofia_declaration(
            description={"en": "Ecological transition.", "fr": "Transition écologique."},
            icon="/assets/connectors/sofia.svg",
        ),
    ]

    assert _connectors() == [
        {
            "slug": "datagouv",
            "name": "data.gouv.fr",
            "description": None,
            "icon": None,
            # The frontend's name for the flag, as in FEATURE_FLAGS.
            "feature_flag": "datagouv-connector",
        },
        {
            "slug": "sofia",
            "name": "SofIA",
            "description": {"en": "Ecological transition.", "fr": "Transition écologique."},
            "icon": "/assets/connectors/sofia.svg",
            "feature_flag": None,
        },
    ]


def test_the_url_is_never_listed(settings):
    """Nor the tier, the timeouts or the instructions written for the model."""
    settings.MCP_CONNECTORS = [datagouv_declaration(url="https://internal.example.org/mcp")]

    response = APIClient().get("/api/v1.0/config/")

    assert "internal.example.org" not in response.content.decode()
    assert set(response.json()["connectors"][0]) == {
        "slug",
        "name",
        "description",
        "icon",
        "feature_flag",
    }


def test_a_refused_declaration_is_not_listed(settings):
    """Fail closed: what the agent will not use, the UI does not offer."""
    settings.MCP_CONNECTORS = [sofia_declaration(read_timout=10), datagouv_declaration()]

    assert [connector["slug"] for connector in _connectors()] == ["datagouv"]
