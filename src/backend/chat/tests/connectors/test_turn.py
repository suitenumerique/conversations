"""The generic per-turn connector state: `UserConnector` and `TurnConnectors`.

Built on connectors that are not data.gouv, so nothing here passes by virtue of
data.gouv's own names.
"""

# pylint: disable=protected-access  # tests intentionally access private members

import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import FunctionToolResultEvent, ToolReturnPart

from chat.connectors import ConnectorDefinition
from chat.connectors.runtime import ConnectorToolset
from chat.connectors.turn import TurnConnectors, UserConnector
from chat.factories import UserFactory
from chat.turn.event_mapper import (
    CONNECTOR_UNAVAILABLE_EVENT_TYPE,
    TurnEventMapper,
    connector_unavailable_notice,
)
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db


def _definition(slug, name, **overrides):
    """A partner connector nobody gates to a cohort, unless overridden."""
    return ConnectorDefinition.from_dict(
        {
            "slug": slug,
            "name": name,
            "url": f"https://{slug}.example.org/mcp",
            "tier": "partner",
            "instructions": f"Use the {name} tools for {name} questions.",
            **overrides,
        }
    )


SOFIA = _definition("sofia", "SofIA", init_timeout=2, read_timeout=0)
DOCS = _definition("docs", "Docs", feature_flag="datagouv_connector")


@pytest.fixture(name="_opted_in")
def opted_in_fixture():
    """Every user opted in to every connector, standing in for #985's opt-in."""
    with patch("chat.connectors.turn.user_opted_in", return_value=True) as opted_in:
        yield opted_in


@pytest.fixture(name="_declared")
def declared_fixture():
    """The deployment declares SofIA and Docs."""
    with patch("chat.connectors.turn.declared_connectors", return_value=[SOFIA, DOCS]):
        yield


@pytest.fixture(name="user")
def user_fixture():
    """A user, built outside the event loop the async tests run in."""
    return UserFactory()


def _turn(user=None):
    """The connectors as they stand for a user. The pk only tags log lines."""
    return TurnConnectors.for_user(user or UserFactory(), uuid4())


def _log_events(caplog):
    """(event, connector_id) for the warnings the connector modules raised."""
    return [
        (record.msg["event"], record.msg["connector_id"])
        for record in caplog.records
        if record.name == "chat.mcp_servers"
    ]


# --- One connector -----------------------------------------------------------


def test_a_connector_without_a_feature_flag_is_enabled_for_everyone(_opted_in):
    """No flag, no cohort: the analytics provider is not even asked."""
    with patch("chat.connectors.turn.is_feature_enabled") as is_enabled:
        connector = UserConnector.for_user(SOFIA, UserFactory(), uuid4())

    assert connector.enabled is True
    is_enabled.assert_not_called()


@pytest.mark.parametrize("in_cohort", [True, False])
def test_a_connector_with_a_feature_flag_is_gated_to_its_cohort(_opted_in, in_cohort):
    """The flag the declaration names is the one asked about."""
    user = UserFactory()
    with patch("chat.connectors.turn.is_feature_enabled", return_value=in_cohort) as is_enabled:
        connector = UserConnector.for_user(DOCS, user, uuid4())

    assert connector.enabled is in_cohort
    is_enabled.assert_called_once_with(user, "datagouv_connector")


def test_the_opt_in_is_read_for_this_connector(_opted_in):
    """The opt-in is asked about the connector being built, not a fixed one."""
    user = UserFactory()

    connector = UserConnector.for_user(SOFIA, user, uuid4())

    assert connector.opted_in is True
    _opted_in.assert_called_once_with(user, SOFIA)


def test_the_connector_is_named_by_its_slug(_opted_in):
    """Tool prefix, events and analytics all key on the slug."""
    assert UserConnector.for_user(SOFIA, UserFactory(), uuid4()).slug == "sofia"


def test_toolsets_are_built_from_the_definition(_opted_in):
    """URL and timeouts come from the declaration; the server never writes our prompt."""
    connector = UserConnector.for_user(SOFIA, UserFactory(), uuid4())

    with patch("chat.connectors.turn.MCPToolset") as mcp_toolset:
        toolsets = connector.toolsets()

    mcp_toolset.assert_called_once_with(
        "https://sofia.example.org/mcp",
        include_instructions=False,
        init_timeout=2,
        # `0` in the declaration: no limit.
        read_timeout=None,
    )
    mcp_toolset.return_value.prefixed.assert_called_once_with("sofia")
    assert len(toolsets) == 1
    assert isinstance(toolsets[0], ConnectorToolset)


def test_the_real_toolset_is_prefixed_with_the_slug(_opted_in):
    """The tools reach the model as `sofia_*`."""
    toolsets = UserConnector.for_user(SOFIA, UserFactory(), uuid4()).toolsets()

    assert toolsets[0].prefix == "sofia"
    assert toolsets[0].wrapped.wrapped.include_instructions is False


@pytest.mark.asyncio
async def test_an_outage_is_reported_in_the_connector_own_words(_opted_in, user):
    """The failed result the model is shown names this connector, not another."""
    connector = UserConnector.for_user(SOFIA, user, uuid4())
    toolset = connector.toolsets()[0]
    toolset.wrapped = MagicMock(call_tool=AsyncMock(side_effect=httpx.ConnectError("gone")))

    for _ in range(2):
        with pytest.raises(ToolFailed, match="SofIA could not be reached"):
            await toolset.call_tool("sofia_search", {}, MagicMock(), MagicMock())

    assert connector.call_failed is True


@pytest.mark.asyncio
async def test_each_connector_instructs_the_model_in_its_own_words(_opted_in, user):
    """Available, forced and unreachable wordings all come from the definition."""
    connector = UserConnector.for_user(SOFIA, user, uuid4())
    toolset = connector.toolsets()[0]

    assert await toolset.get_instructions(None) == SOFIA.instructions

    connector.force()
    assert await toolset.get_instructions(None) == SOFIA.forced_instruction

    connector.mark_connected(False)
    assert await toolset.get_instructions(None) == SOFIA.unreachable_instruction


# --- Every connector of the turn ---------------------------------------------


def test_the_turn_holds_one_connector_per_declaration(_declared, _opted_in):
    """In declaration order, so the model sees them in a stable order."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=True):
        connectors = _turn()

    assert [connector.slug for connector in connectors] == ["sofia", "docs"]
    assert connectors.get("docs").definition is DOCS
    assert connectors.get("datagouv") is None


def test_nothing_declared_means_no_connector(_opted_in):
    """A deployment that declares nothing contacts nothing."""
    with patch("chat.connectors.turn.declared_connectors", return_value=[]):
        assert not list(_turn())


def test_forcing_one_connector_leaves_the_others_alone(_declared, _opted_in):
    """A force names the connector it is for."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=True):
        connectors = _turn()

    connectors.force(["docs"])

    assert [connector.slug for connector in connectors.forced()] == ["docs"]
    assert connectors.get("sofia").forced is False


def test_a_force_the_cohort_denies_is_logged_and_dropped(_declared, _opted_in, caplog):
    """A force never widens access, and operators are told the button misfired."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=False):
        connectors = _turn()

    with caplog.at_level(logging.WARNING, logger="chat.mcp_servers"):
        connectors.force(["docs"])

    assert connectors.forced() == []
    assert connectors.get("docs").toolsets() == []
    assert _log_events(caplog) == [("connector_forced_but_not_enabled", "docs")]


def test_a_force_on_an_undeclared_connector_is_logged_and_dropped(_declared, _opted_in, caplog):
    """The deployment does not declare it: nothing to force, nothing contacted."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=True):
        connectors = _turn()

    with caplog.at_level(logging.WARNING, logger="chat.mcp_servers"):
        connectors.force(["github"])

    assert connectors.forced() == []
    assert _log_events(caplog) == [("connector_forced_but_not_enabled", "github")]


def test_only_the_connector_that_failed_owes_a_notice(_declared, _opted_in):
    """Two forced connectors, one outage: one notice, for the right one."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=True):
        connectors = _turn()
    connectors.force(["sofia", "docs"])
    for connector in connectors:
        connector.mark_connected(True)

    connectors.get("docs").record_call_outage("docs_search")

    assert [connector.slug for connector in connectors.take_outages()] == ["docs"]
    assert connectors.take_outages() == []


def test_outages_on_several_connectors_are_all_taken_at_once(_declared, _opted_in):
    """Taking one connector's outage does not swallow another's."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=True):
        connectors = _turn()
    connectors.force(["sofia", "docs"])
    for connector in connectors:
        connector.mark_connected(True)
        connector.record_call_outage(f"{connector.slug}_search")

    assert [connector.slug for connector in connectors.take_outages()] == ["sofia", "docs"]


# --- The stream --------------------------------------------------------------


def test_the_notice_names_the_connector_it_is_about():
    """The frontend reads the connector off the notice."""
    assert connector_unavailable_notice("sofia").data == [
        {"type": CONNECTOR_UNAVAILABLE_EVENT_TYPE, "kind": "chat_notice", "connector_id": "sofia"}
    ]


@pytest.mark.asyncio
async def test_a_failed_tool_result_streams_the_notice_of_its_connector(_declared, _opted_in, user):
    """With several connectors in the turn, the notice is for the one that failed."""
    with patch("chat.connectors.turn.is_feature_enabled", return_value=True):
        connectors = _turn(user)
    connectors.force(["sofia", "docs"])
    for connector in connectors:
        connector.mark_connected(True)
    connectors.get("sofia").record_call_outage("sofia_search")
    failed = ToolReturnPart(
        tool_name="sofia_search",
        content=SOFIA.unreachable_message,
        tool_call_id="call-1",
        outcome="failed",
    )

    @asynccontextmanager
    async def stream(_run_ctx):
        """A tool-call node streaming the one failed result."""

        async def events():
            yield FunctionToolResultEvent(part=failed)

        yield events()

    mapper = TurnEventMapper(
        trail=MagicMock(),
        meter=MagicMock(),
        check_stop=AsyncMock(),
        model_configuration=MagicMock(),
        supports_streaming=True,
        fake_streaming_delay=0,
        connectors=connectors,
    )
    events = [
        event async for event in mapper._handle_call_tools_node(MagicMock(stream=stream), None)
    ]

    notices = [
        event.data[0]["connector_id"]
        for event in events
        if isinstance(event, events_v4.DataPart)
        and event.data[0]["type"] == CONNECTOR_UNAVAILABLE_EVENT_TYPE
    ]
    assert notices == ["sofia"]


# --- The standing opt-in -----------------------------------------------------


@pytest.mark.parametrize(
    ("allowed", "available"),
    [(["sofia"], True), (["docs"], False), ([], False), (["datagouv"], False)],
)
def test_any_connector_is_opted_in_by_its_slug(allowed, available):
    """`allowed_connectors` is read for every connector, not only data.gouv."""
    user = UserFactory(allowed_connectors=allowed)

    assert UserConnector.for_user(SOFIA, user, uuid4()).available is available


def test_an_opt_in_never_stands_in_for_the_cohort():
    """Opted in, outside the cohort: not available, and a force does not change that."""
    user = UserFactory(allowed_connectors=["docs"])
    with patch("chat.connectors.turn.is_feature_enabled", return_value=False):
        connector = UserConnector.for_user(DOCS, user, uuid4())

    connector.force()

    assert connector.available is False
    assert not connector.toolsets()
