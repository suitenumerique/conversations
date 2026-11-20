"""TurnConnectors: every offered connector, for one user and one turn."""

# pylint: disable=protected-access  # tests intentionally access private members

import logging
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from asgiref.sync import sync_to_async

from core.feature_flags.flags import FeatureToggle

from chat.connectors import TurnConnectors
from chat.factories import UserFactory

pytestmark = pytest.mark.django_db


def _declaration(slug, **overrides):
    return {
        "slug": slug,
        "name": slug.capitalize(),
        "url": f"http://127.0.0.1:9/{slug}",
        "instructions": f"Use the {slug} tools.",
    } | overrides


@pytest.fixture(autouse=True)
def _two_connectors(settings):
    """Two declared connectors, no data.gouv: the generic path, end to end."""
    settings.DATAGOUV_CONNECTOR_URL = ""
    settings.MCP_CONNECTORS = [
        _declaration("legi"),
        _declaration("insee", feature_flag="web_search"),
    ]


def _turn(**user_fields):
    return TurnConnectors.for_user(UserFactory(**user_fields), uuid4())


def test_every_offered_connector_is_resolved_for_the_user():
    """One UserConnector per declaration, in order, opted in by slug."""
    turn = _turn(allowed_connectors=["insee"])

    assert [c.connector_id for c in turn.connectors] == ["legi", "insee"]
    assert turn.get("legi").available is False
    assert turn.get("insee").available is True


def test_a_connector_without_a_flag_is_enabled_for_everyone():
    """No cohort gate: the opt-in alone decides."""
    turn = _turn(allowed_connectors=["legi"])

    assert turn.get("legi").enabled is True
    assert turn.get("legi").available is True


def test_a_connector_outside_its_cohort_is_not_enabled(feature_flags):
    """The flag gates its connector, and only its connector."""
    feature_flags.web_search = FeatureToggle.DISABLED
    turn = _turn(allowed_connectors=["legi", "insee"])

    assert turn.get("insee").enabled is False
    assert turn.get("legi").enabled is True


def test_only_available_or_forced_connectors_build_toolsets():
    """Consent or a force, connector by connector."""
    turn = _turn(allowed_connectors=["legi"])
    turn.force(["insee"])

    assert [c.connector_id for c in turn.connectors if c.toolsets()] == ["legi", "insee"]
    assert turn.get("legi").forced is False
    assert turn.get("insee").forced is True


def test_forcing_an_unknown_connector_is_logged_and_ignored(caplog):
    """The frontend may be older or newer than the deployment."""
    turn = _turn()

    with caplog.at_level(logging.WARNING, logger="chat.connectors.turn"):
        turn.force(["nope", "legi", "legi"])

    assert turn.get("legi").forced is True
    assert [r.msg["connector_id"] for r in caplog.records] == ["nope"]


@pytest.mark.asyncio
async def test_one_unreachable_connector_does_not_drop_the_other():
    """Each connector is entered on its own: one down, the other still serves the turn."""
    turn = await _async_turn(allowed_connectors=["legi", "insee"])
    turn.force(["legi", "insee"])

    async def enter(_stack, toolsets, timeout):
        """`legi` connects, `insee` does not."""
        del timeout
        return toolsets if toolsets[0].prefix == "legi" else []

    with patch("chat.connectors.turn.enter_mcp_toolsets", new=AsyncMock(side_effect=enter)):
        async with AsyncExitStack() as stack:
            connected = await turn.enter(stack)

    assert [t.prefix for t in connected.toolsets] == ["legi"]
    assert [(c.connector_id, ok) for c, ok in connected.forced] == [
        ("legi", True),
        ("insee", False),
    ]
    assert [c.connector_id for c in turn.absent] == ["insee"]
    assert turn.unreachable_forced_instructions() == (
        turn.get("insee").definition.unreachable_instruction
    )


@pytest.mark.asyncio
async def test_each_connector_is_entered_on_its_own_deadline(settings):
    """A slow connector's init_timeout is its own, not the other's."""
    settings.MCP_CONNECTORS = [
        _declaration("legi", init_timeout=1),
        _declaration("insee", init_timeout=7),
    ]
    turn = await _async_turn(allowed_connectors=["legi", "insee"])

    with patch("chat.connectors.turn.enter_mcp_toolsets", new=AsyncMock(return_value=[])) as enter:
        async with AsyncExitStack() as stack:
            await turn.enter(stack)

    assert [call.kwargs["timeout"] for call in enter.await_args_list] == [1, 7]


def test_outages_are_taken_connector_by_connector():
    """Each forced connector that fails mid-run owes exactly one notice."""
    turn = _turn()
    turn.force(["legi", "insee"])
    for connector in turn.connectors:
        connector.mark_connected(True)

    turn.get("insee").record_call_outage("insee_search")
    assert turn.take_outages() == ["insee"]
    assert turn.take_outages() == []
    # Failing mid-run is the toolset's to say, not the agent's.
    assert turn.unreachable_forced_instructions() == ""


async def _async_turn(**user_fields):
    """`_turn`, from async code: building it touches the database."""
    return await sync_to_async(_turn)(**user_fields)
