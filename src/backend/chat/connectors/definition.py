"""What a connector is, as data: `ConnectorDefinition`.

A definition describes one remote MCP server — who it is, where it is, how far
we trust it and what the model is told about it — and nothing else. It holds no
per-turn state and does no I/O, so it can be built from anywhere (settings
today, a catalogue later) and shared freely. See issue #956.
"""

import enum
import re
from dataclasses import dataclass

# Tool names, history and approvals are keyed on the slug, so it stays short,
# lowercase and safe to use as a tool-name prefix.
SLUG_PATTERN = re.compile(r"^[a-z0-9_]{1,20}$")


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
class ConnectorDefinition:
    """One connector, as an immutable value.

    Built once per turn from its source and read, never written, by the code
    that uses it. Holds a reference to nothing secret.
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
