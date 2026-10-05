"""Connectors: the MCP toolsets available to a user, and how to enter them.

`DataGouvConnector` holds one connector's state for one turn: whether it is
enabled at all, the opt-in, the force, and what a failure owes the user.
The caller (see AIAgentService) tells it what happens and asks it what to do; it
owns none of the streaming, the analytics or the agent wiring around that.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import UUID

from django.conf import settings

import httpx
from mcp.shared.exceptions import McpError
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset

from core.feature_flags.helpers import is_feature_enabled
from core.models import User

from chat.clients.schema import ContextDeps

# How a connector we cannot reach surfaces when its toolset is entered: the MCP
# client raises a bare RuntimeError for refused connections and handshake
# timeouts, and passes HTTP and protocol errors through untouched. TimeoutError
# is ours, from the budget enter_mcp_toolsets puts on the whole connection.
CONNECTOR_UNAVAILABLE_ERRORS = (RuntimeError, McpError, httpx.HTTPError, TimeoutError)

# What the model is shown in place of a tool result the connector never gave.
UNREACHABLE_MESSAGE = (
    "data.gouv.fr could not be reached. Do not call its tools again for this request."
)

logger = logging.getLogger(__name__)


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
    data.gouv.fr produces one. The log line names the tool if it ever does.

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
    instructions: Callable[[], str]
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
            raise ToolFailed(UNREACHABLE_MESSAGE)
        try:
            return await super().call_tool(name, tool_args, ctx, tool)
        except Exception as error:
            if not is_connector_unreachable(error):
                raise
            self.down = True
            self.on_unreachable(name)
            raise ToolFailed(UNREACHABLE_MESSAGE) from error


@dataclass
class DataGouvConnector:
    """The DataGouv connector's state for one turn.

    Lives as long as the turn does, like the service that holds it: `force` is
    recorded once at the start and read by everything after it, so an instance
    is not reusable across turns.

    The booleans are read against each other, never alone — `enabled` and
    `opted_in` decide with `forced` whether the toolsets are built at all, and
    `call_failed` decides with `forced` and `unreachable` whether the turn owes
    the user a notice. That is why they live together.
    """

    # The connector's name in code, events and tool names, never shown to a
    # user. Mirrored by the frontend, which reads it off the notice.
    connector_id: ClassVar[str] = "datagouv"

    conversation_pk: UUID
    enabled: bool
    opted_in: bool
    forced: bool = False
    unreachable: bool = False
    call_failed: bool = False

    @classmethod
    def for_user(cls, user: User, conversation_pk: UUID) -> "DataGouvConnector":
        """The connector as it stands for this user, before the turn says anything.

        `enabled` is the pair of gates that do not depend on the turn: the
        deployment configures the connector, and the user is in its beta cohort.
        The user's own opt-in is not one of them — forcing the connector from the
        chat box stands in for it, so that decision belongs to the turn.

        The cohort check runs second because it may reach the analytics
        provider, while the URL check is local. It blocks, so callers must stay
        off the event loop.
        """
        return cls(
            conversation_pk=conversation_pk,
            enabled=bool(settings.DATAGOUV_CONNECTOR_URL)
            and is_feature_enabled(user, "datagouv_connector"),
            opted_in=user.allow_datagouv_connector,
        )

    @property
    def available(self) -> bool:
        """Enabled, and the user has opted in to it.

        A force stands in for the opt-in for one turn, so a forced turn uses the
        connector without being available — see `toolsets`.
        """
        return self.enabled and self.opted_in

    def force(self) -> None:
        """Record that the user demanded the connector this turn.

        A force stands in for the opt-in but never for the two gates under it:
        the deployment's configuration and the beta cohort still decide whether
        the connector exists for this user at all.

        A force the gates deny is silent to the user by design, so it is logged
        instead: the button is shown on the cohort flag alone, and a deployment
        that sets the flag without DATAGOUV_CONNECTOR_URL has no other symptom.
        """
        if not self.enabled:
            logger.warning(
                "%s was forced for conversation %s but is not enabled: the "
                "deployment does not configure it, or the user is outside its cohort.",
                self.connector_id,
                self.conversation_pk,
            )
            return

        self.forced = True

    def toolsets(self) -> list[AbstractToolset[ContextDeps]]:
        """The connector's toolsets for this turn, or none.

        Available, or forced — call `force` first, since a forced turn gets the
        toolsets without the standing opt-in.
        """
        if not (self.available or self.forced):
            return []

        return [
            ConnectorToolset(
                MCPToolset(
                    settings.DATAGOUV_CONNECTOR_URL,
                    # The server may publish tools, descriptions and results; it
                    # may never append to the agent's instructions. Set
                    # explicitly rather than left to the library default: see
                    # docs/tools.md.
                    include_instructions=False,
                    # Two separate bounds: init_timeout covers connect and the
                    # initialize handshake, read_timeout each tool call
                    # afterwards. The library's read_timeout default is five
                    # minutes, long enough for a stalled server to cost the user
                    # their turn. `0` means no limit, which both parameters
                    # spell as None.
                    init_timeout=settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT or None,
                    read_timeout=settings.DATAGOUV_CONNECTOR_READ_TIMEOUT or None,
                ).prefixed(self.connector_id),
                self.record_call_outage,
                self.instruction,
            )
        ]

    def mark_connected(self, connected: bool) -> None:
        """Record what entering the toolsets found. Only meaningful once forced.

        A connector the user demanded and that we could not reach does not cost
        them the turn — it costs the answer its source, and the answer has to
        say so.
        """
        self.unreachable = not connected
        if not connected:
            logger.warning(
                "DataGouv was forced but could not be reached for conversation %s",
                self.conversation_pk,
            )

    def record_call_outage(self, tool_name: str) -> None:
        """Remember that a tool call could not reach the server.

        Handed to `ConnectorToolset` by `toolsets`, so it runs at the tool-call
        boundary rather than in the event stream: the notice itself waits for
        the tool result the model is about to be shown.
        """
        logger.warning(
            "DataGouv could not be reached by its tool %s for conversation %s",
            tool_name,
            self.conversation_pk,
        )
        self.call_failed = True

    def take_outage(self) -> bool:
        """Whether the turn now owes the user a connector-unavailable notice.

        Consumes the recorded failure, so it answers True at most once. False on
        a turn that did not force the connector, on a failure that is not an
        outage — a tool that answers with an error, or arguments the model got
        wrong, neither of which reaches `record_call_outage` — and on the
        retries that follow a failure already reported.
        """
        if not self.call_failed:
            return False
        self.call_failed = False
        if not self.forced or self.unreachable:
            return False

        self.unreachable = True
        return True

    def instruction(self) -> str:
        """What the connector's tools are for, or what a force obliges.

        Read by the connector's toolset on every model request, and by the
        agent only on a forced turn whose connection failed, when there is no
        toolset to carry it. The server's descriptions say how to use each tool
        but never when, so an available turn gets our own guidance on when to
        reach for them.

        One instruction for every outcome because it is read on every model
        request: a forced call that fails mid-run flips `unreachable`, and the
        requests that follow carry the unavailable wording instead.

        The connector's tools come from the MCP server under a `datagouv_`
        prefix and are not known statically, so the instruction names the source
        rather than one tool.
        """
        if self.unreachable:
            return (
                "data.gouv.fr could not be reached for this request. Answer "
                "from your own knowledge or other tools,"
                " and tell the user you could not "
                "consult data.gouv.fr."
            )
        if self.forced:
            return "You must use the data.gouv.fr tools before answering the user request."
        return (
            "The data.gouv.fr tools search France's open-data catalogue: datasets, "
            "the organisations that publish them, and public APIs. Use them when the "
            "answer depends on official French public data (statistics, registries, "
            "local facilities, prices, figures for a commune or département), or "
            "when the user asks for a dataset, a file or an API. This includes "
            "stable administrative facts that official registers record, such as "
            "INSEE codes, the département of a commune or the number of communes: "
            "consult the tools even when you believe you know the answer, rather "
            "than answering from memory. Do not use them for questions about "
            "other countries, history, definitions of concepts, administrative "
            "procedures, writing or coding tasks, or "
            "questions about the user's attached documents."
        )


async def enter_mcp_toolsets(
    stack: AsyncExitStack,
    toolsets: list[AbstractToolset[ContextDeps]],
    timeout: float | None,
) -> list[AbstractToolset[ContextDeps]]:
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
                "Connector %s unavailable, continuing without it",
                getattr(toolset, "prefix", "unknown"),
                exc_info=True,
            )
    return connected
