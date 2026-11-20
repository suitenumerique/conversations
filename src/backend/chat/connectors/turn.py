"""The connectors of one turn: `UserConnector` for one, `TurnConnectors` for all.

`UserConnector` holds one connector's state for one turn: whether it is enabled
at all, the opt-in, the force, and what a failure owes the user.
`TurnConnectors` holds every offered connector for the turn and answers the
questions the agent service and the event mapper ask about them as a group.
The caller (see AIAgentService) tells them what happens and asks them what to
do; they own none of the streaming, the analytics or the agent wiring around
that.
"""

from collections.abc import Iterable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from core.feature_flags.helpers import is_feature_enabled
from core.models import User

from chat.clients.schema import ContextDeps
from chat.connectors.auth import connector_client_kwargs
from chat.connectors.definition import ConnectorDefinition
from chat.connectors.registry import connector_definitions
from chat.connectors.runtime import ConnectorToolset, enter_mcp_toolsets

logger = structlog.get_logger(__name__)


@dataclass
class UserConnector:  # pylint: disable=too-many-instance-attributes
    """One connector's state for one turn.

    Lives as long as the turn does, like the service that holds it: `force` is
    recorded once at the start and read by everything after it, so an instance
    is not reusable across turns.

    The booleans are read against each other, never alone — `enabled` and
    `opted_in` decide with `forced` whether the toolsets are built at all, and
    `call_failed` decides with `forced` and `unreachable` whether the turn owes
    the user a notice. That is why they live together.
    """

    definition: ConnectorDefinition
    user: User
    conversation_pk: UUID
    enabled: bool
    opted_in: bool
    # Whether the user's account is linked, for a connector that authenticates
    # each user (`user_oauth`); always True for the others.
    linked: bool = True
    forced: bool = False
    unreachable: bool = False
    call_failed: bool = False

    @classmethod
    def for_user(
        cls, definition: ConnectorDefinition, user: User, conversation_pk: UUID
    ) -> "UserConnector":
        """The connector as it stands for this user, before the turn says anything.

        `enabled` is the gate that does not depend on the turn: the user is in
        the connector's cohort (the deployment already offers it, or there
        would be no definition). The user's own opt-in is not part of it —
        forcing the connector from the chat box stands in for it, so that
        decision belongs to the turn.

        The cohort check may reach the analytics provider. It blocks, so
        callers must stay off the event loop.
        """
        return cls(
            definition=definition,
            user=user,
            conversation_pk=conversation_pk,
            enabled=definition.feature_flag is None
            or is_feature_enabled(user, definition.feature_flag),
            opted_in=user.has_allowed_connector(definition.slug),
            linked=not definition.auth.needs_linking
            or user.connector_credentials.filter(connector_id=definition.slug).exists(),
        )

    @property
    def connector_id(self) -> str:
        """The connector's name in code, events and analytics."""
        return self.definition.slug

    @property
    def available(self) -> bool:
        """Enabled, and the user has opted in to it.

        A force stands in for the opt-in for one turn, so a forced turn uses the
        connector without being available — see `toolsets`.
        """
        return self.enabled and self.opted_in and self.linked

    def force(self) -> None:
        """Record that the user demanded the connector this turn.

        A force stands in for the opt-in but never for the cohort gate under it.
        A force the gate denies is silent to the user by design, so it is
        logged instead.
        """
        if not self.enabled:
            logger.warning(
                "connector_forced_but_not_enabled",
                connector_id=self.connector_id,
                conversation_id=self.conversation_pk,
            )
            return

        self.forced = True

    def toolsets(self) -> list[AbstractToolset[ContextDeps]]:
        """The connector's toolsets for this turn, or none.

        Available, or forced — call `force` first, since a forced turn gets the
        toolsets without the standing opt-in.
        """
        if not (self.available or self.forced) or not self.linked:
            return []

        definition = self.definition
        return [
            ConnectorToolset(
                MCPToolset(
                    definition.url,
                    # The server may publish tools, descriptions and results; it
                    # may never append to the agent's instructions. Set
                    # explicitly rather than left to the library default: see
                    # docs/tools.md.
                    include_instructions=False,
                    # Two separate bounds: init_timeout covers connect and the
                    # initialize handshake, read_timeout each tool call
                    # afterwards. The library's read_timeout default is five
                    # minutes, long enough for a stalled server to cost the user
                    # their turn. None means no limit.
                    init_timeout=definition.init_timeout,
                    read_timeout=definition.read_timeout,
                    # Credentials, when the connector needs any: see auth.py.
                    **connector_client_kwargs(definition, self.user),
                ).prefixed(definition.slug),
                self.record_call_outage,
                self.instruction,
                unreachable_message=definition.unreachable_message,
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
                "connector_forced_but_unreachable",
                connector_id=self.connector_id,
                conversation_id=self.conversation_pk,
            )

    def record_call_outage(self, tool_name: str) -> None:
        """Remember that a tool call could not reach the server.

        Handed to `ConnectorToolset` by `toolsets`, so it runs at the tool-call
        boundary rather than in the event stream: the notice itself waits for
        the tool result the model is about to be shown.
        """
        logger.warning(
            "connector_tool_call_unreachable",
            connector_id=self.connector_id,
            tool_name=tool_name,
            conversation_id=self.conversation_pk,
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
        toolset to carry it.

        One instruction for every outcome because it is read on every model
        request: a forced call that fails mid-run flips `unreachable`, and the
        requests that follow carry the unavailable wording instead.
        """
        if self.unreachable:
            return self.definition.unreachable_instruction
        if self.forced:
            return self.definition.forced_instruction
        return self.definition.instructions


@dataclass
class ConnectedToolsets:
    """What entering a turn's connectors found."""

    toolsets: list[AbstractToolset[ContextDeps]] = field(default_factory=list)
    # The forced connectors, each with whether it could be reached.
    forced: list[tuple[UserConnector, bool]] = field(default_factory=list)


@dataclass
class TurnConnectors:
    """Every connector the deployment offers, as it stands for one turn."""

    connectors: list[UserConnector]
    conversation_pk: UUID
    # Forced connectors whose tools never reached the run: their toolset is
    # not there to carry their instruction, so the agent must.
    absent: list[UserConnector] = field(default_factory=list)

    @classmethod
    def for_user(cls, user: User, conversation_pk: UUID) -> "TurnConnectors":
        """Every offered connector, resolved for this user. Blocking: see `for_user`."""
        return cls(
            connectors=[
                UserConnector.for_user(definition, user, conversation_pk)
                for definition in connector_definitions().values()
            ],
            conversation_pk=conversation_pk,
        )

    def get(self, slug: str) -> UserConnector | None:
        """The connector with this slug, or None when the deployment does not offer it."""
        return next((c for c in self.connectors if c.connector_id == slug), None)

    def force(self, slugs: Iterable[str]) -> None:
        """Record the connectors the user demanded this turn.

        A slug the deployment does not offer is logged and ignored, like a
        force the cohort denies: the frontend may be older than the deployment.
        """
        for slug in dict.fromkeys(slugs):
            connector = self.get(slug)
            if connector is None:
                logger.warning(
                    "connector_forced_but_not_offered",
                    connector_id=slug,
                    conversation_id=self.conversation_pk,
                )
                continue
            connector.force()

    async def enter(self, stack: AsyncExitStack) -> ConnectedToolsets:
        """Connect every connector this turn uses, dropping the unreachable ones.

        One connector at a time, each on its own deadline, so one that is down
        costs only its own `init_timeout` and never another connector its tools.
        """
        result = ConnectedToolsets()
        for connector in self.connectors:
            toolsets = connector.toolsets()
            if not toolsets:
                # A forced connector with nothing to enter — one whose account
                # the user has not linked — is as absent as an unreachable one.
                if connector.forced:
                    connector.mark_connected(False)
                    result.forced.append((connector, False))
                    self.absent.append(connector)
                continue
            connected = await enter_mcp_toolsets(
                stack, toolsets, timeout=connector.definition.init_timeout
            )
            result.toolsets.extend(connected)
            if connector.forced:
                connector.mark_connected(bool(connected))
                result.forced.append((connector, bool(connected)))
                if not connected:
                    self.absent.append(connector)
        return result

    def unreachable_forced_instructions(self) -> str:
        """The instructions of forced connectors whose tools never reached the run.

        Their toolset is not there to carry them, so the agent does. A forced
        connector that fails mid-run is not one of them: its toolset is in the
        run and switches to the unavailable wording itself. Empty when there
        are none.
        """
        return "\n\n".join(connector.instruction() for connector in self.absent)

    def take_outages(self) -> list[str]:
        """The connectors that now owe the user a notice. See `take_outage`."""
        return [connector.connector_id for connector in self.connectors if connector.take_outage()]
