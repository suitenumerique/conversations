"""Connectors: the MCP toolsets available to a user, and how to enter them.

Whether a connector is actually used is not decided here — the opt-in and the
per-turn force both live in the caller (see AIAgentService).
"""

import asyncio
import logging
from contextlib import AsyncExitStack

from django.conf import settings

import httpx
from mcp.shared.exceptions import McpError
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from core.feature_flags.helpers import is_feature_enabled
from core.models import User

from chat.clients.schema import ContextDeps

DATAGOUV_CONNECTOR_ID = "datagouv"

# How a connector we cannot reach surfaces when its toolset is entered: the MCP
# client raises a bare RuntimeError for refused connections and handshake
# timeouts, and passes HTTP and protocol errors through untouched. TimeoutError
# is ours, from the budget enter_mcp_toolsets puts on the whole connection.
CONNECTOR_UNAVAILABLE_ERRORS = (RuntimeError, McpError, httpx.HTTPError, TimeoutError)

logger = logging.getLogger(__name__)


def datagouv_available(user: User) -> bool:
    """Whether the DataGouv connector exists for this user at all.

    The two gates that do not depend on the turn: the deployment configures
    the connector, and the user is in its beta cohort. The user's own opt-in
    is not one of them — forcing the connector from the chat box stands in for
    it, so that decision belongs to the turn (see CONTEXT.md, "Force").

    The cohort check runs last because it may reach the analytics provider,
    while the URL check is local. It blocks, so callers must stay off the
    event loop.
    """
    if not settings.DATAGOUV_CONNECTOR_URL:
        return False

    return is_feature_enabled(user, "datagouv_connector")


def build_datagouv_toolsets() -> list[AbstractToolset[ContextDeps]]:
    """Build the DataGouv toolset. Callers check `datagouv_available` first."""
    return [
        MCPToolset(
            settings.DATAGOUV_CONNECTOR_URL,
            # The server may publish tools, descriptions and results; it may
            # never append to the agent's instructions. Set explicitly rather
            # than left to the library default: see docs/tools.md.
            include_instructions=False,
            # Two separate bounds: init_timeout covers connect and the
            # initialize handshake, read_timeout each tool call afterwards.
            # The library's read_timeout default is five minutes, long enough
            # for a stalled server to cost the user their turn. `0` means no
            # limit, which both parameters spell as None.
            init_timeout=settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT or None,
            read_timeout=settings.DATAGOUV_CONNECTOR_READ_TIMEOUT or None,
        ).prefixed(DATAGOUV_CONNECTOR_ID)
    ]


async def enter_mcp_toolsets(
    stack: AsyncExitStack, toolsets: list[AbstractToolset[ContextDeps]]
) -> list[AbstractToolset[ContextDeps]]:
    """Connect to each toolset, dropping the ones that cannot be reached.

    A third-party connector being down must never cost the user their turn, so
    a connector we fail to reach is logged and left out of this turn. The user
    is told only when they asked for the connector by forcing it; automatic use
    stays silent, and that notice is raised by the caller, not here.

    The connection carries our own deadline rather than the client's: the MCP
    client's init_timeout covers the protocol handshake but not the transport
    connect underneath it, which would otherwise wait on httpx's defaults when
    a server accepts the connection and then stalls.

    The cost of failing open is that a RuntimeError from a genuine bug in the
    client reads here as an outage. The traceback is logged either way.
    """
    connected = []
    for toolset in toolsets:
        try:
            # `0` means no limit, which asyncio.timeout spells as None.
            async with asyncio.timeout(settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT or None):
                connected.append(await stack.enter_async_context(toolset))
        except CONNECTOR_UNAVAILABLE_ERRORS:
            logger.warning(
                "Connector %s unavailable, continuing without it",
                getattr(toolset, "prefix", "unknown"),
                exc_info=True,
            )
    return connected
