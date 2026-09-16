"""Connectors: the MCP toolsets a user has opted into."""

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

CONNECTOR_ID = "datagouv"

# How a connector we cannot reach surfaces when its toolset is entered: the MCP
# client raises a bare RuntimeError for refused connections and handshake
# timeouts, and passes HTTP and protocol errors through untouched. TimeoutError
# is ours, from the budget enter_mcp_toolsets puts on the whole connection.
CONNECTOR_UNAVAILABLE_ERRORS = (RuntimeError, McpError, httpx.HTTPError, TimeoutError)

logger = logging.getLogger(__name__)


def get_mcp_toolsets(user: User) -> list[AbstractToolset[ContextDeps]]:
    """Return the MCP toolsets this user has opted into.

    Three gates, all required: the connector is configured for this
    deployment, the user is in the beta cohort, and the user switched it on.
    The cohort check runs last because it may reach the analytics provider,
    while the other two are local.
    """
    if not settings.DATAGOUV_CONNECTOR_URL:
        return []

    if not user.allow_datagouv_connector:
        return []

    if not is_feature_enabled(user, "datagouv_connector"):
        return []

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
        ).prefixed(CONNECTOR_ID)
    ]


async def enter_mcp_toolsets(
    stack: AsyncExitStack, toolsets: list[AbstractToolset[ContextDeps]]
) -> list[AbstractToolset[ContextDeps]]:
    """Connect to each toolset, dropping the ones that cannot be reached.

    A third-party connector being down must never cost the user their turn, so
    a connector we fail to reach is logged and left out of this turn. Telling
    the user about it is issue #729.

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
