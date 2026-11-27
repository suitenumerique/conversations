"""data.gouv is declared in `MCP_CONNECTORS` like any other connector."""

import pytest

from chat.connectors import Tier
from chat.connectors.registry import declared_connectors
from chat.connectors.turn import user_opted_in
from chat.factories import UserFactory
from chat.tests.connectors.declarations import (
    DATAGOUV_INSTRUCTIONS,
    DATAGOUV_SLUG,
    datagouv_declaration,
)

# What the model was shown before the abstraction, verbatim.
FORCED_BEFORE = "You must use the data.gouv.fr tools before answering the user request."
UNREACHABLE_INSTRUCTION_BEFORE = (
    "data.gouv.fr could not be reached for this request. Answer "
    "from your own knowledge or other tools,"
    " and tell the user you could not "
    "consult data.gouv.fr."
)
UNREACHABLE_MESSAGE_BEFORE = (
    "data.gouv.fr could not be reached. Do not call its tools again for this request."
)


@pytest.fixture(name="datagouv")
def datagouv_fixture(settings):
    """data.gouv, declared as docs/tools.md tells operators to."""
    settings.MCP_CONNECTORS = [datagouv_declaration()]
    [definition] = declared_connectors()
    return definition


def test_the_slug_is_kept(datagouv):
    """Opt-ins, tool names and analytics are keyed on it."""
    assert datagouv.slug == DATAGOUV_SLUG == "datagouv"


def test_the_documented_declaration_is_what_data_gouv_used_to_be(datagouv):
    """Same endpoint, tier, bounds and cohort as the settings it replaces."""
    assert datagouv.name == "data.gouv.fr"
    assert datagouv.url == "https://mcp.data.gouv.fr/mcp"
    assert datagouv.tier is Tier.PARTNER
    assert datagouv.init_timeout == 5.0
    assert datagouv.read_timeout == 30.0
    assert datagouv.feature_flag == "datagouv_connector"


def test_the_model_sees_the_same_wordings_as_before(datagouv):
    """Derived from `name`, the wordings are the ones data.gouv used to hard-code."""
    assert datagouv.instructions == DATAGOUV_INSTRUCTIONS
    assert datagouv.forced_instruction == FORCED_BEFORE
    assert datagouv.unreachable_instruction == UNREACHABLE_INSTRUCTION_BEFORE
    assert datagouv.unreachable_message == UNREACHABLE_MESSAGE_BEFORE


def test_left_out_of_the_declaration_it_does_not_exist(settings):
    """A deployment that does not declare data.gouv does not offer it, nor contact it."""
    settings.MCP_CONNECTORS = []

    assert not declared_connectors()


def test_the_old_settings_are_gone(settings):
    """`DATAGOUV_CONNECTOR_*` no longer configures anything."""
    for name in (
        "DATAGOUV_CONNECTOR_URL",
        "DATAGOUV_CONNECTOR_INIT_TIMEOUT",
        "DATAGOUV_CONNECTOR_READ_TIMEOUT",
    ):
        assert not hasattr(settings, name), name


@pytest.mark.django_db
@pytest.mark.parametrize(("allowed", "opted_in"), [(["datagouv"], True), ([], False)])
def test_the_opt_in_is_the_slug_in_allowed_connectors(datagouv, allowed, opted_in):
    """data.gouv is opted in like any other connector: by its slug."""
    user = UserFactory(allowed_connectors=allowed)

    assert user_opted_in(user, datagouv) is opted_in
