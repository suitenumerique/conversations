"""One user's connectors for one turn: `UserConnector` and `TurnConnectors`.

`UserConnector` holds one connector's state for one turn: whether it is
enabled at all, the opt-in, the force, and what a failure owes the user.
`TurnConnectors` holds all of them. The caller (see AIAgentService) tells them
what happens and asks them what to do; they own none of the streaming, the
analytics or the agent wiring around that.
"""

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from uuid import UUID

import structlog
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from core.feature_flags.helpers import is_feature_enabled
from core.models import User

from chat.clients.schema import ContextDeps
from chat.connectors.datagouv import user_opted_in
from chat.connectors.definition import ConnectorDefinition
from chat.connectors.registry import declared_connectors
from chat.connectors.runtime import ConnectorToolset

# Not __name__: the name connector log lines have always had.
logger = structlog.get_logger("chat.mcp_servers")


@dataclass
class UserConnector:
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
    conversation_pk: UUID
    enabled: bool
    opted_in: bool
    forced: bool = False
    unreachable: bool = False
    call_failed: bool = False

    @classmethod
    def for_user(
        cls, definition: ConnectorDefinition, user: User, conversation_pk: UUID
    ) -> "UserConnector":
        """The connector as it stands for this user, before the turn says anything.

        `enabled` is the gate that does not depend on the turn once the
        deployment declares the connector: the user is in its cohort. The user's
        own opt-in is not part of it — forcing the connector from the chat box
        stands in for it, so that decision belongs to the turn.

        The cohort check may reach the analytics provider. It blocks, so
        callers must stay off the event loop.
        """
        return cls(
            definition=definition,
            conversation_pk=conversation_pk,
            enabled=definition.feature_flag is None
            or is_feature_enabled(user, definition.feature_flag),
            opted_in=user_opted_in(user, definition),
        )

    @property
    def slug(self) -> str:
        """The connector's name in code, events, analytics and tool names."""
        return self.definition.slug

    @property
    def available(self) -> bool:
        """Enabled, and the user has opted in to it.

        A force stands in for the opt-in for one turn, so a forced turn uses the
        connector without being available — see `toolsets`.
        """
        return self.enabled and self.opted_in

    def force(self) -> None:
        """Record that the user demanded the connector this turn.

        A force stands in for the opt-in but never for the gates under it: the
        deployment's declaration and the cohort still decide whether the
        connector exists for this user at all.

        A force the gates deny is silent to the user by design, so it is logged
        instead: the button may be shown when the connector is not usable.
        """
        if not self.enabled:
            logger.warning(
                "connector_forced_but_not_enabled",
                connector_id=self.slug,
                conversation_id=self.conversation_pk,
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
                    self.definition.url,
                    # The server may publish tools, descriptions and results; it
                    # may never append to the agent's instructions. Set
                    # explicitly rather than left to the library default: see
                    # docs/tools.md.
                    include_instructions=False,
                    # Two separate bounds: init_timeout covers connect and the
                    # initialize handshake, read_timeout each tool call
                    # afterwards. None means no limit.
                    init_timeout=self.definition.init_timeout,
                    read_timeout=self.definition.read_timeout,
                ).prefixed(self.slug),
                self.record_call_outage,
                self.instruction,
                self.definition.unreachable_message,
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
                connector_id=self.slug,
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
            connector_id=self.slug,
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

        The connector's tools come from the MCP server under the slug's prefix
        and are not known statically, so the wordings name the source rather
        than one tool.
        """
        if self.unreachable:
            return self.definition.unreachable_instruction
        if self.forced:
            return self.definition.forced_instruction
        return self.definition.instructions


@dataclass
class TurnConnectors:
    """Every connector the deployment declares, as it stands for one user this turn.

    Built afresh for each turn (see AIAgentService), so a connector removed
    from the declarations, or a user leaving a cohort, takes effect on the next
    turn.
    """

    connectors: list[UserConnector]
    conversation_pk: UUID

    @classmethod
    def for_user(cls, user: User, conversation_pk: UUID) -> "TurnConnectors":
        """The declared connectors, in declaration order. Blocks, like the cohort check."""
        return cls(
            connectors=[
                UserConnector.for_user(definition, user, conversation_pk)
                for definition in declared_connectors()
            ],
            conversation_pk=conversation_pk,
        )

    def __iter__(self) -> Iterator[UserConnector]:
        return iter(self.connectors)

    def get(self, slug: str) -> UserConnector | None:
        """The connector with this slug, or None when the deployment does not declare it."""
        return next((connector for connector in self.connectors if connector.slug == slug), None)

    def force(self, slugs: Collection[str]) -> None:
        """Record the connectors the user demanded this turn.

        A force on a connector the deployment does not declare is dropped and
        logged, like one the cohort denies: a force never widens access.
        """
        for slug in slugs:
            if connector := self.get(slug):
                connector.force()
            else:
                logger.warning(
                    "connector_forced_but_not_enabled",
                    connector_id=slug,
                    conversation_id=self.conversation_pk,
                )

    def forced(self) -> list[UserConnector]:
        """The connectors this turn forced and the gates allowed."""
        return [connector for connector in self.connectors if connector.forced]

    def take_outages(self) -> list[UserConnector]:
        """The connectors that now owe the user a notice, each consumed once.

        Every connector is asked, so one connector's outage never hides another's.
        """
        return [connector for connector in self.connectors if connector.take_outage()]
