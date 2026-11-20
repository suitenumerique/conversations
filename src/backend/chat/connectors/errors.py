"""How a connector we cannot reach shows up, whichever connector it is."""

import httpx
from mcp.shared.exceptions import McpError

# How a connector we cannot reach surfaces when its toolset is entered: the MCP
# client raises a bare RuntimeError for refused connections and handshake
# timeouts, and passes HTTP and protocol errors through untouched. TimeoutError
# is ours, from the budget enter_mcp_toolsets puts on the whole connection.
CONNECTOR_UNAVAILABLE_ERRORS = (RuntimeError, McpError, httpx.HTTPError, TimeoutError)


def is_connector_unreachable(error: BaseException) -> bool:
    """Whether a failed tool call means the server could not be reached.

    A tool that answers with an error is not an outage: the MCP client turns
    those into a ModelRetry caused by a fastmcp ToolError, which is none of
    CONNECTOR_UNAVAILABLE_ERRORS. It reserves protocol errors, transport errors
    and timeouts for a server that never answered, and may deliver any of them
    inside an exception group or behind a ModelRetry it raised `from` them.

    `RuntimeError` is in that tuple for the connection boundary, where a refused
    connection surfaces as one. Here it is broader than it needs to be: a client
    bug reads as an outage. The direction of that failure is benign — the user
    is told a source was missing, and still gets an answer — so the breadth is
    kept rather than guessed at. A protocol-level rejection — a server replying
    `-32602` rather than failing the tool — reads as an outage for the same
    reason: it is an McpError, and splitting the two would be guesswork until
    a connector's server produces one. The log line names the tool if it ever
    does.

    Only `__cause__` is followed, not `__context__`: a library that re-raises
    without `from` is not claiming the original is the reason, and reading an
    incidental context as an outage would be a guess.
    """
    if isinstance(error, BaseExceptionGroup):
        return any(is_connector_unreachable(nested) for nested in error.exceptions)
    if isinstance(error, CONNECTOR_UNAVAILABLE_ERRORS):
        return True
    return error.__cause__ is not None and is_connector_unreachable(error.__cause__)
