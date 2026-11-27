"""`chat.E101`: a deployment with a declaration it cannot use fails `manage.py check`."""

from django.core.management import call_command
from django.core.management.base import SystemCheckError

import pytest

from chat.checks import check_connector_declarations
from chat.tests.connectors.declarations import datagouv_declaration, sofia_declaration

BAD_DECLARATIONS = {
    "invalid JSON": "[{",
    "not a list": '{"slug": "sofia"}',
    "unknown field": [sofia_declaration(read_timout=10)],
    "missing tier": [{k: v for k, v in sofia_declaration().items() if k != "tier"}],
    "bad slug": [sofia_declaration(slug="Sof-IA")],
    "duplicate slug": [sofia_declaration(), sofia_declaration()],
    "unknown flag": [sofia_declaration(feature_flag="no_such_flag")],
    "negative timeout": [sofia_declaration(read_timeout=-1)],
    "unhashable slug": [sofia_declaration(slug=["sofia"])],
    "flag that is not a toggle": [sofia_declaration(feature_flag="model_dump")],
    "malformed url": [sofia_declaration(url="https://exa mple.org/mcp")],
    "infinite timeout": '[{"slug": "sofia", "name": "SofIA", "url": "https://s.example.org/mcp", '
    '"tier": "partner", "instructions": "x", "read_timeout": Infinity}]',
    "colliding tool prefixes": [sofia_declaration(slug="geo"), sofia_declaration(slug="geo_ign")],
}


def test_valid_declarations_pass(settings):
    """data.gouv and a second connector, declared as documented."""
    settings.MCP_CONNECTORS = [datagouv_declaration(), sofia_declaration()]

    assert check_connector_declarations(None) == []


def test_no_declaration_passes(settings):
    """Connectors are optional."""
    settings.MCP_CONNECTORS = "[]"

    assert check_connector_declarations(None) == []


@pytest.mark.parametrize("value", BAD_DECLARATIONS.values(), ids=BAD_DECLARATIONS.keys())
def test_every_bad_declaration_is_an_e101(settings, value):
    """Each problem is reported, all under one id operators can search for."""
    settings.MCP_CONNECTORS = value

    errors = check_connector_declarations(None)

    assert errors
    assert {error.id for error in errors} == {"chat.E101"}
    assert all(error.is_serious() for error in errors)


def test_each_bad_declaration_is_its_own_error(settings):
    """Fixing one does not hide the next."""
    settings.MCP_CONNECTORS = [
        sofia_declaration(read_timout=10),
        datagouv_declaration(),
        sofia_declaration(slug="docs", feature_flag="no_such_flag"),
    ]

    assert len(check_connector_declarations(None)) == 2


@pytest.mark.django_db
def test_manage_py_check_fails_on_a_bad_declaration(settings):
    """The deployment stops here rather than at the first user's turn."""
    settings.MCP_CONNECTORS = [sofia_declaration(read_timout=10)]

    with pytest.raises(SystemCheckError, match="chat.E101"):
        call_command("check")


# What Helm's wait-for-the-database loop runs until it succeeds.
DATABASE_PROBE = "from django.db import connection; connection.ensure_connection()"


@pytest.mark.django_db
def test_the_database_probe_does_not_run_the_connector_check(settings):
    """Helm's wait loop must not read a bad declaration as a database down.

    The probe connects and runs no system check, so a configuration error does
    not keep the loop waiting forever: the migrate command after it reports
    chat.E101 instead.
    """
    settings.MCP_CONNECTORS = [sofia_declaration(read_timout=10)]

    call_command("shell", command=DATABASE_PROBE)


@pytest.mark.django_db
def test_migrate_reports_a_bad_declaration(settings):
    """What the Helm migrate job runs once the database answers."""
    settings.MCP_CONNECTORS = [sofia_declaration(read_timout=10)]

    with pytest.raises(SystemCheckError, match="chat.E101"):
        # skip_checks=False: call_command skips them by default; manage.py does not.
        call_command("migrate", "--no-input", "--check", skip_checks=False)
