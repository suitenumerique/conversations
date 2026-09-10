"""Connectors: the MCP toolsets a user has opted into."""

import logging
from contextlib import AsyncExitStack

from django.conf import settings

import httpx
from mcp.shared.exceptions import McpError
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from core.feature_flags.helpers import is_feature_enabled

CONNECTOR_ID = "datagouv"

# How a connector we cannot reach surfaces when its toolset is entered: the MCP
# client raises a bare RuntimeError for refused connections and handshake
# timeouts, and passes HTTP and protocol errors through untouched.
CONNECTOR_UNAVAILABLE_ERRORS = (RuntimeError, McpError, httpx.HTTPError)

logger = logging.getLogger(__name__)


def get_mcp_toolsets(user) -> list[AbstractToolset]:
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
            # never append to the agent's instructions. See ADR 0003.
            include_instructions=False,
            init_timeout=settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT,
        ).prefixed(CONNECTOR_ID)
    ]


async def enter_mcp_toolsets(
    stack: AsyncExitStack, toolsets: list[AbstractToolset]
) -> list[AbstractToolset]:
    """Connect to each toolset, dropping the ones that cannot be reached.

    A third-party connector being down must never cost the user their turn, so
    a connector we fail to reach is logged and left out of this turn. Telling
    the user about it is issue #729.
    """
    connected = []
    for toolset in toolsets:
        try:
            connected.append(await stack.enter_async_context(toolset))
        except CONNECTOR_UNAVAILABLE_ERRORS:
            logger.warning(
                "Connector %s unavailable, continuing without it",
                CONNECTOR_ID,
                exc_info=True,
            )
    return connected
