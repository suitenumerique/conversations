"""One connector's declaration and per-turn state, whichever connector it is.

A connector is one remote MCP server a user has switched on for themselves.
`ConnectorSpec` declares everything that differs between connectors — where it
is configured, who may use it, and what the model is told about it — so adding
a connector is adding a spec, not a new state machine. `Connector` holds one
connector's state for one turn: whether it is enabled at all, the opt-in, the
force, and what a failure owes the user.
"""

from dataclasses import dataclass
from uuid import UUID

from django.conf import settings

import structlog
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from core.feature_flags.helpers import is_feature_enabled
from core.models import User

from chat.clients.schema import ContextDeps
from chat.connectors.toolset import ConnectorToolset

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ConnectorSpec:  # pylint: disable=too-many-instance-attributes
    """Everything that differs between connectors, in one place.

    Adding a connector means adding one of these (plus its deployment settings,
    its cohort flag, and its opt-in column on `User` — see below), not a new
    state machine.
    """

    connector_id: str
    # `settings` attribute names, read lazily so tests may override them. An
    # empty URL keeps the connector inert: not offered, not built, never
    # contacted. `0` timeouts mean no limit.
    url_setting: str
    init_timeout_setting: str
    read_timeout_setting: str
    # Feature-flag name for the beta cohort, and `User` attribute for the
    # standing opt-in. Both are per connector on purpose: consent names the
    # source the assistant may consult.
    feature_flag: str
    opt_in_attribute: str
    # What the model is shown in place of a tool result the connector never gave.
    unavailable_tool_message: str
    # What the connector's tools are for, or what a force obliges. Read on
    # every model request: a forced call that fails mid-run flips
    # `unreachable`, and the requests that follow carry the unavailable wording.
    available_instruction: str
    forced_instruction: str
    unreachable_instruction: str


@dataclass
class Connector:
    """One connector's state for one turn.

    Lives as long as the turn does, like the service that holds it: `force` is
    recorded once at the start and read by everything after it, so an instance
    is not reusable across turns.

    The booleans are read against each other, never alone — `enabled` and
    `opted_in` decide with `forced` whether the toolsets are built at all, and
    `call_failed` decides with `forced` and `unreachable` whether the turn owes
    the user a notice. That is why they live together.
    """

    spec: ConnectorSpec
    conversation_pk: UUID
    enabled: bool
    opted_in: bool
    forced: bool = False
    unreachable: bool = False
    call_failed: bool = False

    @classmethod
    def for_user(cls, user: User, conversation_pk: UUID, spec: ConnectorSpec) -> "Connector":
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
            spec=spec,
            conversation_pk=conversation_pk,
            enabled=bool(getattr(settings, spec.url_setting))
            and is_feature_enabled(user, spec.feature_flag),
            opted_in=bool(getattr(user, spec.opt_in_attribute)),
        )

    @property
    def connector_id(self) -> str:
        """The connector's name in code, events and tool names, never shown to a user."""
        return self.spec.connector_id

    @property
    def init_timeout(self) -> float | None:
        """This turn's connection budget, or None for no limit (`0` disables it)."""
        return getattr(settings, self.spec.init_timeout_setting) or None

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
        that sets the flag without a connector URL has no other symptom.
        """
        if not self.enabled:
            # The deployment does not configure it, or the user is outside its cohort.
            logger.warning(
                "connector_forced_but_not_enabled",
                connector_id=self.spec.connector_id,
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

        url = getattr(settings, self.spec.url_setting)
        return [
            ConnectorToolset(
                MCPToolset(
                    url,
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
                    init_timeout=getattr(settings, self.spec.init_timeout_setting) or None,
                    read_timeout=getattr(settings, self.spec.read_timeout_setting) or None,
                ).prefixed(self.spec.connector_id),
                self.record_call_outage,
                self.instruction,
                unreachable_message=self.spec.unavailable_tool_message,
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
                connector_id=self.spec.connector_id,
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
            connector_id=self.spec.connector_id,
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
        toolset to carry it. The server's descriptions say how to use each tool
        but never when, so an available turn gets our own guidance on when to
        reach for them.

        One instruction for every outcome because it is read on every model
        request: a forced call that fails mid-run flips `unreachable`, and the
        requests that follow carry the unavailable wording instead.
        """
        if self.unreachable:
            return self.spec.unreachable_instruction
        if self.forced:
            return self.spec.forced_instruction
        return self.spec.available_instruction
