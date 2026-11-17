"""The turn-independent machinery every connector is built on.

`ConnectorToolset` is a connector's toolset as the agent sees it: its tools,
and what they are for. `enter_mcp_toolsets` connects a turn's toolsets,
dropping the ones that cannot be reached.
"""

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from mcp.shared.exceptions import McpError
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.toolsets import ToolsetTool, WrapperToolset

from chat.clients.schema import ContextDeps

# How a connector we cannot reach surfaces when its toolset is entered: the MCP
# client raises a bare RuntimeError for refused connections and handshake
# timeouts, and passes HTTP and protocol errors through untouched. TimeoutError
# is ours, from the budget enter_mcp_toolsets puts on the whole connection.
CONNECTOR_UNAVAILABLE_ERRORS = (RuntimeError, McpError, httpx.HTTPError, TimeoutError)

logger = structlog.get_logger(__name__)


def is_connector_unreachable(error: BaseException) -> bool:
    """Whether a failed tool call means the server could not be reached.

    A tool that answers with an error is not an outage: the MCP client turns
    those into a ModelRetry caused by a fastmcp ToolError, which is none of
    CONNECTOR_UNAVAILABLE_ERRORS. It reserves protocol errors, transport errors
    and timeouts for a server that never answered, and may deliver any of them
    inside an exception group or behind a ModelRetry it raised `from` them.

    `RuntimeError` is in that tuple for the connection boundary, where a
    refused connection surfaces as one. Here it is broader than it needs to be:
    a client bug reads as an outage. The direction of that failure is benign —
    the user is told a source was missing, and still gets an answer — so the
    breadth is kept rather than guessed at. A protocol-level rejection — a
    server replying `-32602` rather than failing the tool — reads as an outage
    for the same reason: it is an McpError, and splitting the two would be
    guesswork until a connector's server produces one. The log line names the
    tool if it ever does.

    Only `__cause__` is followed, not `__context__`: a library that re-raises
    without `from` is not claiming the original is the reason, and reading an
    incidental context as an outage would be a guess.
    """
    if isinstance(error, BaseExceptionGroup):
        return any(is_connector_unreachable(nested) for nested in error.exceptions)
    if isinstance(error, CONNECTOR_UNAVAILABLE_ERRORS):
        return True
    return error.__cause__ is not None and is_connector_unreachable(error.__cause__)


@dataclass
class ConnectorToolset(WrapperToolset[ContextDeps]):
    """A connector's toolset as the agent sees it: its tools, and what they are for.

    It carries the connector's own instruction, so the model is told about the
    tools exactly when it has them: no instruction can name tools that did not
    reach the run.

    It is also the tool-call boundary, the only place that can tell an outage
    from a retry the model brought on itself: argument validation fails before
    the call ever gets here, so what this sees are failures of the call itself.
    An outage is reported, then handed to the model as a failed result rather
    than a retry: waiting out another timeout would not bring the server back,
    and exhausting the retry budget would cost the user their turn. Once the
    server is found down, it is not called again for the rest of the turn.
    """

    on_unreachable: Callable[[str], None]
    instructions: Callable[[str], str]
    unreachable_message: str = (
        "The connector could not be reached. Do not call its tools again for this request."
    )
    down: bool = field(default=False, init=False)

    @property
    def prefix(self) -> str:
        """The wrapped connector's prefix, so logs still name the connector.

        Read with getattr because `wrapped` is typed as the abstract toolset,
        which declares no prefix; every toolset this wraps is a prefixed one.
        """
        return getattr(self.wrapped, "prefix", "unknown")

    async def get_instructions(self, ctx: RunContext[ContextDeps]) -> str:
        """The connector's instruction, read on every model request.

        Not delegated: the server's own instructions are never accepted (see
        `include_instructions=False`). A plain string is dynamic, so the wording
        may change mid-run once an outage is reported.
        """
        return self.instructions()

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[ContextDeps],
        tool: ToolsetTool[ContextDeps],
    ) -> Any:
        if self.down:
            raise ToolFailed(self.unreachable_message)
        try:
            return await super().call_tool(name, tool_args, ctx, tool)
        except Exception as error:
            if not is_connector_unreachable(error):
                raise
            self.down = True
            self.on_unreachable(name)
            raise ToolFailed(self.unreachable_message) from error


async def enter_mcp_toolsets(
    stack: AsyncExitStack,
    toolsets: list,
    timeout: float | None,
) -> list:
    """Connect to each toolset, dropping the ones that cannot be reached.

    A third-party connector being down must never cost the user their turn, so
    a connector we fail to reach is logged and left out of this turn. The user
    is told only when they asked for the connector by forcing it; automatic use
    stays silent, and that notice is raised by the caller, not here.

    The connection carries our own deadline, `timeout` (None for no limit),
    rather than the client's: the MCP
    client's init_timeout covers the protocol handshake but not the transport
    connect underneath it, which would otherwise wait on httpx's defaults when
    a server accepts the connection and then stalls.

    The cost of failing open is that a RuntimeError from a genuine bug in the
    client reads here as an outage. The traceback is logged either way.
    """
    connected = []
    for toolset in toolsets:
        try:
            async with asyncio.timeout(timeout):
                connected.append(await stack.enter_async_context(toolset))
        except CONNECTOR_UNAVAILABLE_ERRORS:
            logger.warning(
                "connector_unavailable",
                connector_id=getattr(toolset, "prefix", "unknown"),
                exc_info=True,
            )
    return connected
