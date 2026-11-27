"""What a connector is, as data: `ConnectorDefinition` and `Tier`.

A definition describes one remote MCP server: who it is, where it is, how far we
trust it, which cohort may use it and what the model is told about it. It holds
no per-turn state, no secret and does no I/O, so it can be built from any
source of plain dictionaries (`MCP_CONNECTORS` through the registry today, a
catalogue later) and shared freely. See docs/adr/0001-connector-trust-tiers.md.
"""

import enum
import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

# Tool names, history and opt-ins are keyed on the slug, so it stays short,
# lowercase and safe to use as a tool-name prefix.
SLUG_PATTERN = re.compile(r"^[a-z0-9_]{1,20}$")

# Seconds, for a declaration that does not say: data.gouv's long-standing
# defaults. The library's own read timeout, five minutes, is long enough for a
# stalled server to cost the user their turn.
DEFAULT_INIT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0

_FIELDS = frozenset(
    {
        "slug",
        "name",
        "url",
        "tier",
        "instructions",
        "init_timeout",
        "read_timeout",
        "feature_flag",
    }
)
_REQUIRED_FIELDS = frozenset({"slug", "name", "url", "tier", "instructions"})


class Tier(enum.StrEnum):
    """How far we trust a connector's operator, not how public its data is.

    Recorded, not enforced yet: nothing behaves differently per tier. Only
    `PARTNER` connectors are shipped; the others are named so the data model
    does not change when they arrive.
    """

    # Same operator, hosting and identity provider as this instance.
    INTERNAL = "internal"
    # A public body or contracted vendor outside our infrastructure.
    PARTNER = "partner"
    # Declared by an end user; nobody reviewed it.
    USER = "user"


def _is_seconds(value: Any) -> bool:
    """A finite number of seconds: not a bool dressed as an int, not NaN or Infinity.

    `json.loads` accepts the `NaN` and `Infinity` literals, and neither compares
    as negative, so they are refused here explicitly.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_http_url(url: str) -> bool:
    """An http(s) URL with a host, that the HTTP client will accept.

    Checked here because a URL the client refuses raises `httpx.InvalidURL`,
    which is not an outage error: it would fail every turn rather than drop
    the connector.
    """
    if any(char.isspace() or not char.isprintable() for char in url):
        return False
    try:
        parts = urlsplit(url)
        httpx.URL(url)
    except ValueError, httpx.InvalidURL:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.hostname)


@dataclass(frozen=True, kw_only=True)
class ConnectorDefinition:  # pylint: disable=too-many-instance-attributes
    """One connector, as an immutable value.

    Built from its declaration and read, never written, by the code that uses
    it. `tier` has no default: a declaration that does not say how far we trust
    the server is refused rather than given one.
    """

    # Identity: `slug` names the connector in code, events, analytics and tool
    # prefixes, and must not change once users opted in; `name` is how the user
    # and the model read it.
    slug: str
    name: str
    # The server's streamable-HTTP endpoint.
    url: str
    tier: Tier
    # When the model should reach for the connector's tools. Written by us,
    # never taken from the server.
    instructions: str
    # Seconds; None means no limit. `init_timeout` bounds connecting and the
    # initialize handshake, `read_timeout` each tool call afterwards.
    init_timeout: float | None = DEFAULT_INIT_TIMEOUT
    read_timeout: float | None = DEFAULT_READ_TIMEOUT
    # The `FeatureFlags` field gating the connector to a cohort, or None for
    # everyone the deployment serves.
    feature_flag: str | None = None

    def __post_init__(self):
        """Refuse a definition the rest of the code could not use safely."""
        if not isinstance(self.slug, str) or not SLUG_PATTERN.match(self.slug):
            raise ValueError(
                f"Invalid connector slug {self.slug!r}: expected {SLUG_PATTERN.pattern}."
            )
        for name in ("name", "url", "instructions"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"Connector {self.slug!r}: {name} must be a non-empty string.")
        if not _is_http_url(self.url):
            raise ValueError(
                f"Connector {self.slug!r}: url must be an http or https URL with a host."
            )
        if not isinstance(self.tier, Tier):
            raise ValueError(
                f"Connector {self.slug!r}: unknown tier {self.tier!r}, "
                f"expected one of {[tier.value for tier in Tier]}."
            )
        for name in ("init_timeout", "read_timeout"):
            value = getattr(self, name)
            if value is not None and (not _is_seconds(value) or value <= 0):
                raise ValueError(
                    f"Connector {self.slug!r}: {name} must be a positive number of "
                    "seconds, or None for no limit."
                )
        if self.feature_flag is not None and (
            not isinstance(self.feature_flag, str) or not self.feature_flag
        ):
            raise ValueError(f"Connector {self.slug!r}: feature_flag must be a flag name, or None.")

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

    @property
    def unreachable_message(self) -> str:
        """What the model is shown in place of a tool result the server never gave."""
        return f"{self.name} could not be reached. Do not call its tools again for this request."

    @classmethod
    def from_dict(cls, data: Any) -> "ConnectorDefinition":
        """A definition from its declaration, a plain dictionary.

        Unknown keys are refused rather than ignored: a misspelt `read_timout`
        silently falling back to a default is the kind of mistake this catches.
        Timeouts follow the settings convention: `0` means no limit, a negative
        value is refused, and an absent one takes the defaults above.

        Raises ValueError on anything it cannot use.
        """
        if not isinstance(data, dict):
            raise ValueError(f"A connector declaration must be an object, not {data!r}.")
        slug = data.get("slug")
        if unknown := set(data) - _FIELDS:
            raise ValueError(f"Connector {slug!r} has unknown fields: {sorted(unknown)}.")
        if missing := _REQUIRED_FIELDS - set(data):
            raise ValueError(f"Connector {slug!r} is missing {sorted(missing)}.")

        try:
            tier = Tier(data["tier"])
        except ValueError:
            # Let __post_init__ name the accepted tiers.
            tier = data["tier"]

        timeouts = {}
        for name, default in (
            ("init_timeout", DEFAULT_INIT_TIMEOUT),
            ("read_timeout", DEFAULT_READ_TIMEOUT),
        ):
            value = data.get(name, default)
            if not _is_seconds(value) or value < 0:
                raise ValueError(
                    f"Connector {slug!r}: {name} must be a number of seconds, 0 for no limit."
                )
            timeouts[name] = value or None

        return cls(
            slug=slug,
            name=data["name"],
            url=data["url"],
            tier=tier,
            instructions=data["instructions"],
            feature_flag=data.get("feature_flag"),
            **timeouts,
        )
