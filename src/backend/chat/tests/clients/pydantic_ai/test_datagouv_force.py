"""Unit tests for forcing the DataGouv connector on a single turn."""

# pylint: disable=protected-access  # tests intentionally access private members

import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import FunctionToolResultEvent, ToolReturnPart

from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import CONNECTOR_UNAVAILABLE_EVENT_TYPE, AIAgentService
from chat.clients.schema import StreamingState
from chat.factories import ChatConversationFactory
from chat.mcp_servers import DataGouvConnector
from chat.tests.clients.pydantic_ai.test_run_agent_summary import _run_agent_patches
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db


@pytest.fixture(name="conversation")
def conversation_fixture():
    """A conversation with an owner."""
    return ChatConversationFactory()


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """A single user message, enough to drive _run_agent."""
    return [UIMessage(id="msg-1", role="user", content="Hello", parts=[])]


@pytest.fixture(name="service")
def service_fixture(conversation, settings):
    """An agent service for a user the connector is available to."""
    settings.DATAGOUV_CONNECTOR_URL = "https://mcp.data.gouv.fr/mcp"
    with patch("chat.mcp_servers.is_feature_enabled", return_value=True):
        yield AIAgentService(
            conversation=conversation,
            user=conversation.owner,
            model_hrid=None,
            language="en-us",
        )


def _toolsets_for(service, *, opted_in, forced):
    """Resolve the per-turn connector decision the way _run_agent does."""
    service._datagouv.opted_in = opted_in
    if forced:
        service._datagouv.force()
    return service._datagouv.toolsets()


def _force(service, *, connected):
    """Force the connector and settle its reachability, the way _run_agent does."""
    service._datagouv.force()
    service._datagouv.mark_connected(connected)
    if not connected:
        service._setup_datagouv_instruction()


async def _toolset_instruction(service):
    """The instruction the connector's toolset hands the model."""
    return await service._datagouv.toolsets()[0].get_instructions(None)


def test_opted_in_user_gets_the_connector(service):
    """Standing consent is enough; no button needed."""
    assert _toolsets_for(service, opted_in=True, forced=False)


def test_user_who_never_opted_in_gets_nothing_by_default(service):
    """Without consent and without a force, the connector stays out."""
    assert not _toolsets_for(service, opted_in=False, forced=False)


def test_forcing_stands_in_for_the_opt_in(service):
    """Asking for the source is consent to use it, for this turn."""
    assert _toolsets_for(service, opted_in=False, forced=True)


def test_forcing_cannot_bypass_availability(conversation):
    """A force never conjures a connector the deployment or cohort denies."""
    with patch("chat.mcp_servers.is_feature_enabled", return_value=False):
        service = AIAgentService(
            conversation=conversation,
            user=conversation.owner,
            model_hrid=None,
            language="en-us",
        )

    assert not _toolsets_for(service, opted_in=True, forced=True)


@pytest.mark.asyncio
async def test_reachable_forced_connector_instructs_the_model_to_use_it(service):
    """A force is an instruction, not just an available tool."""
    _force(service, connected=True)

    instruction = await _toolset_instruction(service)
    assert "must" in instruction.lower()
    assert "data.gouv.fr" in instruction


def test_unreachable_forced_connector_tells_the_model_to_say_so(service):
    """The answer is produced, but it owns up to what it could not consult."""
    _force(service, connected=False)

    instruction = service.conversation_agent._instructions[-1]()
    assert "could not" in instruction.lower()
    assert "data.gouv.fr" in instruction


@pytest.mark.asyncio
async def test_an_unreachable_forced_connector_streams_a_notice(service):
    """The user is told the source was missing, without losing the answer."""
    with patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()):
        events = [event async for event in service._report_forced_connector(connected=False)]

    assert len(events) == 1
    assert isinstance(events[0], events_v4.DataPart)
    assert events[0].data == [
        {
            "type": CONNECTOR_UNAVAILABLE_EVENT_TYPE,
            "kind": "chat_notice",
            "connector_id": "datagouv",
        }
    ]


@pytest.mark.asyncio
async def test_a_reachable_forced_connector_streams_nothing(service):
    """Nothing degraded, nothing to say."""
    with patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()):
        events = [event async for event in service._report_forced_connector(connected=True)]

    assert events == []


@pytest.mark.asyncio
async def test_forcing_is_captured(service):
    """Button usage is the adoption signal the Settings opt-in cannot give."""
    with patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()) as mock_capture:
        _ = [event async for event in service._report_forced_connector(connected=True)]

    mock_capture.assert_awaited_once_with(
        "connector_forced",
        service.user.pk,
        properties={"connector_id": "datagouv", "reachable": True},
    )


@pytest.mark.asyncio
async def test_an_unreachable_forced_tool_call_is_reported_like_an_unreachable_server(service):
    """A connector that answers the handshake and then goes away owes a notice."""
    _force(service, connected=True)
    service._datagouv.record_call_outage("datagouv_search_datasets")

    assert service._datagouv.take_outage() is True
    assert "could not" in (await _toolset_instruction(service)).lower()


def test_an_unreachable_forced_tool_call_is_reported_once(service):
    """The model retries the call; the user is not told twice."""
    _force(service, connected=True)

    service._datagouv.record_call_outage("datagouv_search_datasets")
    assert service._datagouv.take_outage() is True

    service._datagouv.record_call_outage("datagouv_search_datasets")
    assert service._datagouv.take_outage() is False


def test_an_unreachable_tool_call_nobody_forced_stays_silent(service):
    """Automatic use of a source is not worth mentioning when it fails.

    A turn that does not force the connector never records a force, so the
    opted-in user whose tool call fails is told nothing.
    """
    service._datagouv.record_call_outage("datagouv_search_datasets")

    assert service._datagouv.take_outage() is False


@pytest.mark.asyncio
async def test_a_retry_that_is_not_an_outage_stays_silent(service):
    """Bad arguments and a tool answering with an error are not the server dying.

    Both reach the stream as a RetryPromptPart, and neither reaches
    record_call_outage — so the turn keeps the wording that demands the source
    rather than the one that apologises for it.
    """
    _force(service, connected=True)

    assert service._datagouv.take_outage() is False
    instruction = (await _toolset_instruction(service)).lower()
    assert "must" in instruction
    assert "could not" not in instruction


@pytest.mark.asyncio
async def test_an_available_connector_tells_the_model_when_to_use_it(service):
    """The server's descriptions say how to use its tools, never when."""
    service._datagouv.opted_in = True

    instruction = await _toolset_instruction(service)
    assert "data.gouv.fr" in instruction
    assert "must" not in instruction.lower()
    assert "could not" not in instruction.lower()


@pytest.mark.asyncio
async def test_a_failed_tool_result_streams_the_notice(service):
    """An outage reaches the model as a failed result, and the user as a notice."""
    _force(service, connected=True)
    service._datagouv.record_call_outage("datagouv_search_datasets")
    failed = ToolReturnPart(
        tool_name="datagouv_search_datasets",
        content="data.gouv.fr could not be reached.",
        tool_call_id="call-1",
        outcome="failed",
    )

    @asynccontextmanager
    async def stream(_run_ctx):
        """A tool-call node streaming the one failed result."""

        async def events():
            yield FunctionToolResultEvent(part=failed)

        yield events()

    with patch.object(service, "_agent_stop_streaming", AsyncMock()):
        events = [
            event
            async for event in service._handle_call_tools_node(
                MagicMock(stream=stream), None, StreamingState()
            )
        ]

    assert len(_notices(events)) == 1


def test_the_wire_name_is_the_one_the_frontend_listens_for():
    """Mirrored in useChat.tsx; changing it silently breaks the notice."""
    assert CONNECTOR_UNAVAILABLE_EVENT_TYPE == "connector_unavailable"


def _notices(events):
    """The connector-unavailable notices among a turn's events."""
    return [
        event
        for event in events
        if isinstance(event, events_v4.DataPart)
        and event.data[0]["type"] == CONNECTOR_UNAVAILABLE_EVENT_TYPE
    ]


@pytest.mark.asyncio
async def test_a_forced_connector_the_gates_deny_reports_nothing(conversation, ui_messages):
    """Nothing was contacted, so there is no outage to report.

    The deployment or the cohort denying the connector leaves the same empty
    toolset list an unreachable server does. Only the second one is a failure
    the user is owed a word about, and only it belongs in the outage rate.
    """
    with patch("chat.mcp_servers.is_feature_enabled", return_value=False):
        service = AIAgentService(
            conversation=conversation,
            user=conversation.owner,
            model_hrid=None,
            language="en-us",
        )

    with (
        _run_agent_patches(service),
        patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()) as mock_capture,
    ):
        events = [event async for event in service._run_agent(ui_messages, force_datagouv=True)]

    assert _notices(events) == []
    mock_capture.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_forced_connector_that_was_built_but_unreachable_reports_it(service, ui_messages):
    """The connector existed for this user and still could not be reached."""
    with (
        _run_agent_patches(service),
        patch.object(service._datagouv, "toolsets", return_value=[object()]),
        patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=AsyncMock(return_value=[])),
        patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()) as mock_capture,
    ):
        events = [event async for event in service._run_agent(ui_messages, force_datagouv=True)]

    assert len(_notices(events)) == 1
    mock_capture.assert_awaited_once_with(
        "connector_forced",
        service.user.pk,
        properties={"connector_id": "datagouv", "reachable": False},
    )


@pytest.mark.asyncio
async def test_forcing_both_sources_demands_both(service, ui_messages):
    """Two forces in one turn do not compete; the turn honours both.

    Nothing in the turn's setup makes one source displace the other, and this
    pins that down: both setups run, so both instructions reach the model. The
    connector is left unreachable, the one case its instruction goes through
    the agent rather than its toolset.
    """
    with (
        _run_agent_patches(service),
        patch.object(service._datagouv, "toolsets", return_value=[object()]),
        patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=AsyncMock(return_value=[])),
        patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()),
        patch.object(service, "_setup_datagouv_instruction") as setup_datagouv,
    ):
        _ = [
            event
            async for event in service._run_agent(
                ui_messages, force_web_search=True, force_datagouv=True
            )
        ]
        # The web-search setup is a mock only inside the patch stack.
        setup_web_search = service._setup_web_search

    setup_web_search.assert_called_once_with(True)
    setup_datagouv.assert_called_once_with()


@pytest.mark.asyncio
async def test_a_connected_unforced_turn_leaves_the_guidance_to_the_toolset(service, ui_messages):
    """The tools carry their own instruction; the agent is not given a second one."""
    with (
        _run_agent_patches(service),
        patch.object(service._datagouv, "toolsets", return_value=[object()]),
        patch(
            "chat.clients.pydantic_ai.enter_mcp_toolsets",
            new=AsyncMock(return_value=[object()]),
        ),
        patch.object(service, "_setup_datagouv_instruction") as setup_datagouv,
    ):
        _ = [event async for event in service._run_agent(ui_messages)]

    setup_datagouv.assert_not_called()


@pytest.mark.asyncio
async def test_a_turn_without_the_tools_gets_no_guidance(service, ui_messages):
    """No instruction may name tools the model does not have.

    Covers both a user who never opted in and an unforced connector that
    could not be reached: either way, no toolsets reach the run.
    """
    with (
        _run_agent_patches(service),
        patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=AsyncMock(return_value=[])),
        patch.object(service, "_setup_datagouv_instruction") as setup_datagouv,
    ):
        _ = [event async for event in service._run_agent(ui_messages)]

    setup_datagouv.assert_not_called()


def _denied_service(conversation):
    """A service for a user the gates deny the connector to."""
    with patch("chat.mcp_servers.is_feature_enabled", return_value=False):
        return AIAgentService(
            conversation=conversation,
            user=conversation.owner,
            model_hrid=None,
            language="en-us",
        )


def _force_warnings(caplog):
    """The connector-force warnings this module raised, and nothing else.

    Unrelated loggers land in caplog too — token estimation warns on every
    service built.
    """
    return [
        record
        for record in caplog.records
        if record.name == "chat.mcp_servers" and "forced" in record.getMessage()
    ]


def test_a_force_the_gates_deny_is_logged(conversation, caplog):
    """The user is told nothing, by design — so operators are.

    The button is shown on the cohort flag alone, so a deployment that sets
    the flag without DATAGOUV_CONNECTOR_URL has no other symptom.
    """
    service = _denied_service(conversation)

    with caplog.at_level(logging.WARNING, logger="chat.mcp_servers"):
        _toolsets_for(service, opted_in=False, forced=True)

    assert [
        DataGouvConnector.connector_id in record.getMessage() for record in _force_warnings(caplog)
    ] == [True]


def test_an_unavailable_connector_nobody_asked_for_is_silent(conversation, caplog):
    """Most users are outside the cohort; that is not worth a log line."""
    service = _denied_service(conversation)

    with caplog.at_level(logging.WARNING, logger="chat.mcp_servers"):
        _toolsets_for(service, opted_in=True, forced=False)

    assert _force_warnings(caplog) == []
