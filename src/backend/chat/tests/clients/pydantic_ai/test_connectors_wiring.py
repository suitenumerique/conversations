"""The agent loops over the turn's connectors, whichever they are."""

# pylint: disable=protected-access  # tests intentionally access private members

from contextlib import AsyncExitStack, ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from mcp.server.fastmcp import FastMCP
from pydantic_ai.models.test import TestModel

from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.connectors import ConnectorDefinition
from chat.factories import ChatConversationFactory, UserFactory
from chat.tests.clients.pydantic_ai.test_datagouv_connector import _serve
from chat.tests.clients.pydantic_ai.test_run_agent_summary import _run_agent_patches
from chat.tests.connectors.declarations import datagouv_declaration, sofia_declaration
from chat.turn.event_mapper import CONNECTOR_UNAVAILABLE_EVENT_TYPE
from chat.vercel_ai_sdk.core import events_v4

pytestmark = pytest.mark.django_db


def _definition(slug, name, init_timeout):
    """A partner connector open to everyone."""
    return ConnectorDefinition.from_dict(
        {
            "slug": slug,
            "name": name,
            "url": f"https://{slug}.example.org/mcp",
            "tier": "partner",
            "instructions": f"Use the {name} tools.",
            "init_timeout": init_timeout,
        }
    )


SOFIA = _definition("sofia", "SofIA", init_timeout=2)
DOCS = _definition("docs", "Docs", init_timeout=0)


@pytest.fixture(name="service")
def service_fixture():
    """A service for a user opted in to the two connectors the deployment declares."""
    conversation = ChatConversationFactory()
    with (
        patch("chat.connectors.turn.declared_connectors", return_value=[SOFIA, DOCS]),
        patch("chat.connectors.turn.user_opted_in", return_value=True),
    ):
        yield AIAgentService(
            conversation=conversation,
            user=conversation.owner,
            model_hrid=None,
            language="en-us",
        )


@pytest.fixture(name="ui_messages")
def ui_messages_fixture():
    """A single user message, enough to drive _run_agent."""
    return [UIMessage(id="msg-1", role="user", content="Hello", parts=[])]


def _entering(reachable):
    """An enter_mcp_toolsets stand-in: connectors in `reachable` connect, others do not."""

    async def enter(_stack, toolsets, timeout):  # pylint: disable=unused-argument
        return [toolset for toolset in toolsets if toolset.prefix in reachable]

    return AsyncMock(side_effect=enter)


def _built_toolsets(service):
    """Every connector builds a stand-in toolset under its prefix.

    `_run_agent_patches` empties the toolsets so nothing is contacted; this
    puts one back for each connector, for `_entering` to connect or not.
    """
    stack = ExitStack()
    for connector in service._connectors:
        stack.enter_context(
            patch.object(connector, "toolsets", return_value=[MagicMock(prefix=connector.slug)])
        )
    return stack


def _notices(events):
    """The connector ids of the connector-unavailable notices among a turn's events."""
    return [
        event.data[0]["connector_id"]
        for event in events
        if isinstance(event, events_v4.DataPart)
        and event.data[0]["type"] == CONNECTOR_UNAVAILABLE_EVENT_TYPE
    ]


@pytest.mark.asyncio
async def test_every_connector_is_entered_on_its_own_deadline(service):
    """One connector's timeout is not another's; `0` still means no limit."""
    enter = _entering({"sofia", "docs"})

    with patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=enter):
        async with AsyncExitStack() as stack:
            toolsets = await service._enter_connector_toolsets(stack)

    assert [toolset.prefix for toolset in toolsets] == ["sofia", "docs"]
    assert [call.kwargs["timeout"] for call in enter.await_args_list] == [2, None]


@pytest.mark.asyncio
async def test_one_connector_down_does_not_take_the_others_with_it(service):
    """Fail open, connector by connector."""
    with patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=_entering({"docs"})):
        async with AsyncExitStack() as stack:
            toolsets = await service._enter_connector_toolsets(stack)

    assert [toolset.prefix for toolset in toolsets] == ["docs"]


@pytest.mark.asyncio
async def test_the_agent_run_gets_every_connected_connector(service, ui_messages):
    """Both connectors' toolsets reach the same agent run."""
    captured = {}

    with _run_agent_patches(service):

        @asynccontextmanager
        async def capture_iter(*_args, **kwargs):
            captured["toolsets"] = kwargs.get("toolsets")
            async with fake_iter(*_args, **kwargs) as run:
                yield run

        fake_iter = service.conversation_agent.iter
        service.conversation_agent.iter = capture_iter
        with (
            patch.object(service._connectors.get("sofia"), "toolsets", return_value=["s"]),
            patch.object(service._connectors.get("docs"), "toolsets", return_value=["d"]),
            patch(
                "chat.clients.pydantic_ai.enter_mcp_toolsets",
                new=AsyncMock(side_effect=lambda _stack, toolsets, timeout: toolsets),
            ),
        ):
            _ = [event async for event in service._run_agent(ui_messages)]

    assert captured["toolsets"] == ["s", "d"]


@pytest.mark.asyncio
async def test_a_forced_connector_that_cannot_be_reached_is_reported_by_its_slug(
    service, ui_messages
):
    """The notice, the analytics and the model's instruction are all for that connector."""
    with (
        _run_agent_patches(service),
        _built_toolsets(service),
        patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=_entering({"sofia"})),
        patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()) as capture,
        patch.object(service, "_setup_connector_instruction") as setup_instruction,
    ):
        events = [
            event async for event in service._run_agent(ui_messages, force_connectors=["docs"])
        ]

    assert _notices(events) == ["docs"]
    capture.assert_awaited_once_with(
        "connector_forced",
        service.user.pk,
        properties={"connector_id": "docs", "reachable": False},
    )
    setup_instruction.assert_called_once_with(service._connectors.get("docs"))


@pytest.mark.asyncio
async def test_forcing_two_connectors_reports_each(service, ui_messages):
    """Each force is settled on its own: one reached, one not."""
    with (
        _run_agent_patches(service),
        _built_toolsets(service),
        patch("chat.clients.pydantic_ai.enter_mcp_toolsets", new=_entering({"sofia"})),
        patch("chat.clients.pydantic_ai.acapture_event", new=AsyncMock()) as capture,
    ):
        events = [
            event
            async for event in service._run_agent(ui_messages, force_connectors=["sofia", "docs"])
        ]

    assert _notices(events) == ["docs"]
    assert [call.kwargs["properties"] for call in capture.await_args_list] == [
        {"connector_id": "sofia", "reachable": True},
        {"connector_id": "docs", "reachable": False},
    ]


def test_an_unreachable_forced_connector_instructs_the_model_in_its_own_words(service):
    """The agent carries the wording of the connector it could not reach."""
    docs = service._connectors.get("docs")
    service._connectors.force(["docs"])
    docs.mark_connected(False)

    service._setup_connector_instruction(docs)

    assert service.conversation_agent._instructions[-1].instruction() == (
        DOCS.unreachable_instruction
    )


@pytest.fixture(name="sofia_server_url")
def sofia_server_url_fixture():
    """A real MCP server on localhost, standing in for a second partner."""
    server = FastMCP("sofia", stateless_http=True)

    @server.tool()
    def search_corpus(query: str) -> str:
        """Search the ecological transition corpus."""
        return f"corpus results for {query}"

    yield from _serve(server)


@pytest.mark.asyncio
async def test_a_second_connector_needs_only_a_declaration(settings, sofia_server_url):
    """Declared in settings, nothing else: its tools reach the agent under its slug.

    Nothing is patched on the connector path. SofIA has no opt-in field
    until #985, so the turn forces it, which stands in for the opt-in.
    """
    settings.MCP_CONNECTORS = [datagouv_declaration(), sofia_declaration(url=sofia_server_url)]
    user = await sync_to_async(UserFactory)()
    conversation = await sync_to_async(ChatConversationFactory)(owner=user)
    service = await sync_to_async(AIAgentService)(conversation, user=user)

    async with AsyncExitStack() as stack:
        toolsets = await service._enter_connector_toolsets(stack, ["sofia"])
        with service.conversation_agent.override(model=TestModel(), deps=service._context_deps):
            result = await service.conversation_agent.run("Hello.", toolsets=toolsets)

    assert "sofia_search_corpus" in result.output
    assert service._connectors.get("sofia").definition.name == "SofIA"
