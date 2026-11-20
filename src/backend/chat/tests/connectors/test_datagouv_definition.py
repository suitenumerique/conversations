"""data.gouv expressed as a ConnectorDefinition, and what that must not change."""

import importlib
import warnings
from unittest.mock import patch

import pytest

from chat.connectors import (
    DATAGOUV_SLUG,
    ConnectorDefinition,
    Tier,
    UserConnector,
    connector_definitions,
    datagouv_definition,
)
from chat.connectors.datagouv import DATAGOUV_INSTRUCTIONS

URL = "https://mcp.data.gouv.fr/mcp"


def test_unconfigured_deployment_has_no_definition(settings):
    """An empty URL leaves data.gouv out entirely."""
    settings.DATAGOUV_CONNECTOR_URL = ""

    assert datagouv_definition() is None


def test_configured_deployment_builds_the_definition(settings):
    """Every field comes from the settings or from what data.gouv always was."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT = 5.0
    settings.DATAGOUV_CONNECTOR_READ_TIMEOUT = 30.0

    assert datagouv_definition() == ConnectorDefinition(
        slug="datagouv",
        name="data.gouv.fr",
        url=URL,
        tier=Tier.PARTNER,
        instructions=DATAGOUV_INSTRUCTIONS,
        init_timeout=5.0,
        read_timeout=30.0,
        feature_flag="datagouv_connector",
    )


@pytest.mark.parametrize("field", ["init_timeout", "read_timeout"])
def test_zero_timeout_means_no_limit(settings, field):
    """`0` in the settings is spelled None in the definition, as before."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    setattr(settings, f"DATAGOUV_CONNECTOR_{field.upper()}", 0)

    assert getattr(datagouv_definition(), field) is None


def test_definition_follows_the_settings_on_every_call(settings):
    """Built per call, not cached at import, so a settings change is picked up."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    assert datagouv_definition().url == URL

    settings.DATAGOUV_CONNECTOR_URL = ""
    assert datagouv_definition() is None


def test_slug_is_the_historical_connector_id(settings):
    """Tool prefixes, events and the frontend all read `datagouv`."""
    settings.DATAGOUV_CONNECTOR_URL = URL

    assert datagouv_definition().slug == DATAGOUV_SLUG == "datagouv"


def test_the_registry_offers_datagouv_first(settings):
    """data.gouv comes from its own settings, ahead of the declared connectors."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    settings.MCP_CONNECTORS = [
        {"slug": "other", "name": "Other", "url": URL, "instructions": "Use it."}
    ]

    assert list(connector_definitions()) == ["datagouv", "other"]


def test_model_facing_wording_is_unchanged(settings):
    """The words the model reads about data.gouv are pinned to their previous text."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    definition = datagouv_definition()
    assert definition.unreachable_message == (
        "data.gouv.fr could not be reached. Do not call its tools again for this request."
    )
    assert DATAGOUV_INSTRUCTIONS == (
        "The data.gouv.fr tools search France's open-data catalogue: datasets, "
        "the organisations that publish them, and public APIs. Use them when the "
        "answer depends on official French public data (statistics, registries, "
        "local facilities, prices, figures for a commune or département), or "
        "when the user asks for a dataset, a file or an API. Prefer them over "
        "answering such figures from memory. Do not use them for questions about "
        "other countries, general knowledge, administrative procedures, "
        "writing or coding tasks, or "
        "questions about the user's attached documents."
    )


def test_forced_and_unreachable_wording_is_unchanged(settings):
    """What a force and an outage tell the model about data.gouv, as before."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    definition = datagouv_definition()

    assert definition.forced_instruction == (
        "You must use the data.gouv.fr tools before answering the user request."
    )
    assert definition.unreachable_instruction == (
        "data.gouv.fr could not be reached for this request. Answer from your own "
        "knowledge or other tools, and tell the user you could not consult data.gouv.fr."
    )


def test_toolset_is_built_from_the_definition(settings):
    """URL, timeouts, prefix and outage wording all reach the MCP toolset as before."""
    settings.DATAGOUV_CONNECTOR_URL = URL
    settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT = 5.0
    settings.DATAGOUV_CONNECTOR_READ_TIMEOUT = 0
    definition = datagouv_definition()
    connector = UserConnector(
        definition=definition, user=None, conversation_pk=None, enabled=True, opted_in=True
    )

    with patch("chat.connectors.turn.MCPToolset") as mcp_toolset:
        (toolset,) = connector.toolsets()

    mcp_toolset.assert_called_once_with(
        URL, include_instructions=False, init_timeout=5.0, read_timeout=None
    )
    mcp_toolset.return_value.prefixed.assert_called_once_with("datagouv")
    assert toolset.wrapped is mcp_toolset.return_value.prefixed.return_value
    assert toolset.unreachable_message == definition.unreachable_message


def test_the_old_import_path_still_works():
    """`chat.mcp_servers` re-exports the runtime objects for one release, and says so."""
    connectors = importlib.import_module("chat.connectors")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        shim = importlib.reload(importlib.import_module("chat.mcp_servers"))

    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    for name in (
        "CONNECTOR_UNAVAILABLE_ERRORS",
        "ConnectorToolset",
        "enter_mcp_toolsets",
        "is_connector_unreachable",
    ):
        assert getattr(shim, name) is getattr(connectors, name)
