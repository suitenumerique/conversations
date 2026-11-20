"""The data.gouv.fr connector: its definition, and its state for one turn.

`datagouv_definition` expresses data.gouv as a `ConnectorDefinition` built from
the deployment settings. It is a temporary bridge: connectors are meant to be
declared as data (see issue #956), at which point it goes away.

`DataGouvConnector` holds the connector's state for one turn: whether it is
enabled at all, the opt-in, the force, and what a failure owes the user. The
caller (see AIAgentService) tells it what happens and asks it what to do; it
owns none of the streaming, the analytics or the agent wiring around that.
"""

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from django.conf import settings

import structlog
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from core.feature_flags.helpers import is_feature_enabled
from core.models import User

from chat.clients.schema import ContextDeps
from chat.connectors.definition import ConnectorDefinition, Tier
from chat.connectors.runtime import ConnectorToolset

logger = structlog.get_logger(__name__)

# The connector's name in code, events and tool names, never shown to a user.
# Mirrored by the frontend, which reads it off the notice.
DATAGOUV_SLUG = "datagouv"

# What the model is shown in place of a tool result the connector never gave.
UNREACHABLE_MESSAGE = (
    "data.gouv.fr could not be reached. Do not call its tools again for this request."
)

# When the model should reach for the connector's tools. The server's
# descriptions say how to use each tool but never when. The tools come from the
# MCP server under a `datagouv_` prefix and are not known statically, so the
# instruction names the source rather than one tool.
DATAGOUV_INSTRUCTIONS = (
    "The data.gouv.fr tools search France's open-data catalogue: datasets, "
    "the organisations that publish them, and public APIs. Use them when the "
    "answer depends on official French public data (statistics, registries, "
    "local facilities, prices, figures for a commune or département), or "
    "when the user asks for a dataset, a file or an API. Prefer them over "
    "answering such figures from memory. Do not use them for questions about "
    "other countries, general knowledge, administrative procedures, "
    "writing or coding tasks, or "
    "questions about the user's attached documents."
)


def datagouv_definition() -> ConnectorDefinition | None:
    """data.gouv as a definition, or None when the deployment leaves it out.

    Read from settings on every call, so tests may override them. An empty
    `DATAGOUV_CONNECTOR_URL` keeps the connector inert: not offered, not built,
    never contacted. `0` timeouts mean no limit, which the definition spells as
    None.
    """
    if not settings.DATAGOUV_CONNECTOR_URL:
        return None
    return ConnectorDefinition(
        slug=DATAGOUV_SLUG,
        name="data.gouv.fr",
        url=settings.DATAGOUV_CONNECTOR_URL,
        tier=Tier.PARTNER,
        instructions=DATAGOUV_INSTRUCTIONS,
        init_timeout=settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT or None,
        read_timeout=settings.DATAGOUV_CONNECTOR_READ_TIMEOUT or None,
    )


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

    connector_id: ClassVar[str] = DATAGOUV_SLUG

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
            enabled=datagouv_definition() is not None
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
            # The deployment does not configure it, or the user is outside its cohort.
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
        if not (self.available or self.forced):
            return []

        definition = datagouv_definition()
        if definition is None:
            # Unreachable through `for_user`, which needs the URL to enable it.
            return []

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
                ).prefixed(definition.slug),
                self.record_call_outage,
                self.instruction,
                unreachable_message=UNREACHABLE_MESSAGE,
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
        toolset to carry it. An available turn gets `DATAGOUV_INSTRUCTIONS`.

        One instruction for every outcome because it is read on every model
        request: a forced call that fails mid-run flips `unreachable`, and the
        requests that follow carry the unavailable wording instead.
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
        return DATAGOUV_INSTRUCTIONS
