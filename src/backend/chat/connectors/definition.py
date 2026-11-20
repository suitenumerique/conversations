"""What a connector is, as data: `ConnectorDefinition`.

A definition describes one remote MCP server — who it is, where it is, how far
we trust it, how we authenticate to it, which cohort may use it and what the
model is told about it — and nothing else. It holds no per-turn state, no
secret and does no I/O, so it can be built from anywhere (the `MCP_CONNECTORS`
setting, the legacy data.gouv settings, a catalogue later) and shared freely.
See issue #956.
"""

import enum
import re
from dataclasses import dataclass, field
from typing import Any

from chat.connectors.auth import ConnectorAuth

# Tool names, history and approvals are keyed on the slug, so it stays short,
# lowercase and safe to use as a tool-name prefix.
SLUG_PATTERN = re.compile(r"^[a-z0-9_]{1,20}$")

# Seconds, for a declaration that does not say.
DEFAULT_INIT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0


class Tier(enum.StrEnum):
    """How far we trust a connector's operator, not how public its data is.

    Only `PARTNER` connectors exist yet; the other tiers are named so the data
    model does not change when they arrive.
    """

    # Same operator, hosting and identity provider as this instance.
    INTERNAL = "internal"
    # A public body or contracted vendor outside our infrastructure.
    PARTNER = "partner"
    # Declared by an end user; nobody reviewed it.
    USER = "user"


@dataclass(frozen=True, kw_only=True)
class ConnectorDefinition:  # pylint: disable=too-many-instance-attributes
    """One connector, as an immutable value.

    Built from its source and read, never written, by the code that uses it.
    Holds a reference to nothing secret.
    """

    # Identity: `slug` names the connector in code, events and tool prefixes;
    # `name` is how the user and the model read it.
    slug: str
    name: str
    # Endpoint.
    url: str
    tier: Tier
    # When the model should reach for the connector's tools. Written by us,
    # never taken from the server.
    instructions: str
    # Seconds; None means no limit. `init_timeout` bounds connecting and the
    # initialize handshake, `read_timeout` each tool call afterwards.
    init_timeout: float | None = None
    read_timeout: float | None = None
    # The `FeatureFlags` field gating the connector to a cohort, or None for
    # everyone the deployment serves.
    feature_flag: str | None = None
    # How we identify ourselves to the server. Anonymous unless declared.
    auth: ConnectorAuth = field(default_factory=ConnectorAuth)

    def __post_init__(self):
        """Refuse a definition the rest of the code could not use safely."""
        if not SLUG_PATTERN.match(self.slug):
            raise ValueError(
                f"Invalid connector slug {self.slug!r}: expected {SLUG_PATTERN.pattern}"
            )
        if not self.name:
            raise ValueError("A connector needs a name.")
        if not self.url:
            raise ValueError(f"Connector {self.slug!r} needs a URL.")
        if not isinstance(self.tier, Tier):
            raise ValueError(f"Connector {self.slug!r} has an unknown tier {self.tier!r}.")
        if not self.instructions:
            raise ValueError(f"Connector {self.slug!r} needs instructions for the model.")
        for name in ("init_timeout", "read_timeout"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(
                    f"Connector {self.slug!r}: {name} must be positive, or None for no limit."
                )
        if not isinstance(self.auth, ConnectorAuth):
            raise ValueError(f"Connector {self.slug!r} has an invalid auth {self.auth!r}.")

    @property
    def unreachable_message(self) -> str:
        """What the model is shown in place of a tool result the server never gave."""
        return f"{self.name} could not be reached. Do not call its tools again for this request."

    @property
    def forced_instruction(self) -> str:
        """What the model is told when the user demanded the connector this turn."""
        return f"You must use the {self.name} tools before answering the user request."

    @property
    def unreachable_instruction(self) -> str:
        """What the model is told when a forced connector could not be used."""
        return (
            f"{self.name} could not be reached for this request. Answer from your "
            "own knowledge or other tools, and tell the user you could not "
            f"consult {self.name}."
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorDefinition":
        """A definition from its declaration, as written in `MCP_CONNECTORS`.

        Unknown keys are refused rather than ignored: a misspelt `read_timout`
        silently falling back to no limit is the kind of mistake this catches.
        Timeouts follow the settings convention: `0` means no limit; absent
        means the data.gouv defaults, since the library's own read timeout (five
        minutes) is long enough for a stalled server to cost the user the turn.
        """
        allowed = {
            "slug",
            "name",
            "url",
            "tier",
            "instructions",
            "init_timeout",
            "read_timeout",
            "feature_flag",
            "auth",
        }
        if not isinstance(data, dict):
            raise ValueError(f"A connector declaration must be an object, not {data!r}.")
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(
                f"Connector {data.get('slug')!r} has unknown fields: {sorted(unknown)}."
            )
        missing = {"slug", "name", "url", "instructions"} - set(data)
        if missing:
            raise ValueError(f"Connector {data.get('slug')!r} is missing {sorted(missing)}.")
        return cls(
            slug=data["slug"],
            name=data["name"],
            url=data["url"],
            tier=Tier(data.get("tier", Tier.PARTNER)),
            instructions=data["instructions"],
            init_timeout=data.get("init_timeout", DEFAULT_INIT_TIMEOUT) or None,
            read_timeout=data.get("read_timeout", DEFAULT_READ_TIMEOUT) or None,
            feature_flag=data.get("feature_flag") or None,
            auth=ConnectorAuth.from_dict(data.get("auth")),
        )
