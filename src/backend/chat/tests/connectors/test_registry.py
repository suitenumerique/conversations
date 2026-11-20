"""The registry: which connectors the deployment offers."""

import logging

import pytest

from chat.connectors.registry import (
    check_connector_declarations,
    connector_definitions,
    get_connector_definition,
    validate_connector_declarations,
)


def _declaration(slug="legi", **overrides):
    return {
        "slug": slug,
        "name": slug.capitalize(),
        "url": f"https://{slug}.example.org/mcp",
        "instructions": f"Use {slug}.",
    } | overrides


@pytest.fixture(autouse=True)
def _no_datagouv(settings):
    """Leave data.gouv out unless a test puts it back."""
    settings.DATAGOUV_CONNECTOR_URL = ""
    settings.MCP_CONNECTORS = []


def test_nothing_declared_nothing_offered():
    """The default deployment offers no connector."""
    assert connector_definitions() == {}
    assert not validate_connector_declarations()


def test_declared_connectors_are_offered_in_order(settings):
    """Adding a connector is a configuration change, nothing else."""
    settings.MCP_CONNECTORS = [_declaration("legi"), _declaration("insee")]

    assert list(connector_definitions()) == ["legi", "insee"]
    assert get_connector_definition("insee").url == "https://insee.example.org/mcp"
    assert get_connector_definition("nope") is None


@pytest.mark.parametrize(
    "declarations, reason",
    [
        ([_declaration(), _declaration()], "declared twice"),
        (
            [_declaration(auth={"kind": "deployment_token", "token_env": "T"})],
            "not implemented yet",
        ),
        ([_declaration(feature_flag="no_such_flag")], "unknown feature flag"),
        ([_declaration(slug="Not A Slug")], "slug"),
        ("not json", "JSON list"),
    ],
)
def test_an_unusable_declaration_is_left_out_and_reported(settings, caplog, declarations, reason):
    """Lenient at runtime, strict at startup: one typo never costs every user their turn."""
    settings.MCP_CONNECTORS = declarations

    with caplog.at_level(logging.ERROR, logger="chat.connectors.registry"):
        offered = connector_definitions()

    assert len(offered) <= 1  # The first of two duplicates is kept.
    assert any(reason in error for error in validate_connector_declarations())
    assert any(r.msg["event"] == "connector_declaration_refused" for r in caplog.records)


def test_a_declaration_may_name_a_known_feature_flag(settings):
    """The cohort gate is any FeatureFlags field."""
    settings.MCP_CONNECTORS = [_declaration(feature_flag="web_search")]

    assert get_connector_definition("legi").feature_flag == "web_search"


def test_a_datagouv_declaration_clashes_with_its_legacy_settings(settings):
    """data.gouv is either the legacy settings or a declaration, not both."""
    settings.DATAGOUV_CONNECTOR_URL = "https://mcp.data.gouv.fr/mcp"
    settings.MCP_CONNECTORS = [_declaration("datagouv")]

    assert connector_definitions()["datagouv"].url == "https://mcp.data.gouv.fr/mcp"
    assert validate_connector_declarations() == ["Connector slug 'datagouv' is declared twice."]


def test_the_system_check_reports_an_unusable_declaration(settings):
    """The deployment finds out at startup (`manage.py check`), not from its users."""
    settings.MCP_CONNECTORS = [_declaration(auth={"kind": "deployment_token", "token_env": "T"})]

    (error,) = check_connector_declarations()

    assert error.id == "chat.E101"
    assert "not implemented yet" in error.msg
