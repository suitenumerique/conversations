"""How we authenticate to a connector's server.

Two kinds are supported:

- `NONE`: the server is public and reached anonymously.
- `USER_OAUTH`: each user links their own account on the connector's
  authorization server (OAuth 2.1 authorization code with PKCE, as the MCP
  authorization specification requires). The tokens are stored encrypted per
  user and connector (`chat.models.ConnectorCredential`) and refreshed when
  they expire. See `chat.connectors.oauth`.

`DEPLOYMENT_TOKEN` (one secret for the whole deployment, read from the
environment variable the declaration names) is named so the data model does
not change when it lands; declaring it today is refused by the registry, never
silently treated as anonymous.

Whatever the kind, credentials are resolved per turn by
`connector_client_kwargs`, the only function `UserConnector` calls, and handed
to `MCPToolset`. Nothing else in the turn needs to know how a connector
authenticates.
"""

import enum
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat.connectors.definition import ConnectorDefinition


class AuthKind(enum.StrEnum):
    """How a connector's server expects us to identify ourselves."""

    # Anonymous: the server is public.
    NONE = "none"
    # One bearer token for the whole deployment, from an environment variable.
    DEPLOYMENT_TOKEN = "deployment_token"  # noqa: S105  # a kind, not a secret
    # A token per user, from an OAuth authorization-code flow.
    USER_OAUTH = "user_oauth"


# The kinds `connector_client_kwargs` knows how to resolve.
SUPPORTED_AUTH_KINDS = frozenset({AuthKind.NONE, AuthKind.USER_OAUTH})

# The fields each kind accepts besides `kind`.
_FIELDS = {
    AuthKind.NONE: frozenset(),
    AuthKind.DEPLOYMENT_TOKEN: frozenset({"token_env"}),
    AuthKind.USER_OAUTH: frozenset({"client_id", "client_secret_env", "scopes", "issuer"}),
}


class ConnectorAuthNotSupportedError(NotImplementedError):
    """A connector asks for an authentication this deployment cannot provide yet."""


@dataclass(frozen=True, kw_only=True)
class ConnectorAuth:  # pylint: disable=too-many-instance-attributes
    """A connector's authentication, as declared. Holds no secret.

    Secrets are named, never written: `token_env` and `client_secret_env` are
    the environment variables they are read from.

    For `USER_OAUTH`:
    - `client_id`: the OAuth client registered for this deployment with the
      connector's authorization server.
    - `client_secret_env`: for a confidential client; absent for a public one,
      which PKCE alone protects.
    - `scopes`: requested at authorization; empty means those the server
      advertises in its protected resource metadata.
    - `issuer`: the authorization server. Absent means discovered from the
      server itself (RFC 9728), as MCP clients are expected to.
    """

    kind: AuthKind = AuthKind.NONE
    token_env: str | None = None
    client_id: str | None = None
    client_secret_env: str | None = None
    scopes: tuple[str, ...] = ()
    issuer: str | None = None

    def __post_init__(self):
        """Refuse a declaration that could not be resolved, whatever the kind."""
        if not isinstance(self.kind, AuthKind):
            raise ValueError(f"Unknown connector auth kind {self.kind!r}.")
        given = {
            name
            for name in ("token_env", "client_id", "client_secret_env", "scopes", "issuer")
            if getattr(self, name)
        }
        if stray := given - _FIELDS[self.kind]:
            raise ValueError(f"{sorted(stray)} do not apply to a {self.kind} connector.")
        if self.kind == AuthKind.DEPLOYMENT_TOKEN and not self.token_env:
            raise ValueError("A deployment_token connector needs `token_env`.")
        if self.kind == AuthKind.USER_OAUTH and not self.client_id:
            raise ValueError("A user_oauth connector needs `client_id`.")
        if not all(isinstance(scope, str) and scope for scope in self.scopes):
            raise ValueError("`scopes` must be a list of non-empty strings.")

    @property
    def supported(self) -> bool:
        """Whether this deployment can authenticate this way yet."""
        return self.kind in SUPPORTED_AUTH_KINDS

    @property
    def needs_linking(self) -> bool:
        """Whether each user must link their own account before using the connector."""
        return self.kind == AuthKind.USER_OAUTH

    @property
    def client_secret(self) -> str | None:
        """The client secret, read from the environment; None for a public client."""
        if not self.client_secret_env:
            return None
        return os.environ.get(self.client_secret_env) or None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConnectorAuth":
        """The `auth` entry of a declaration; absent means anonymous."""
        if not data:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"A connector auth must be an object, not {data!r}.")
        unknown = set(data) - {
            "kind",
            "token_env",
            "client_id",
            "client_secret_env",
            "scopes",
            "issuer",
        }
        if unknown:
            raise ValueError(f"Unknown connector auth fields: {sorted(unknown)}.")
        scopes = data.get("scopes") or ()
        if isinstance(scopes, str) or not isinstance(scopes, list | tuple):
            raise ValueError("`scopes` must be a list of strings.")
        return cls(
            kind=AuthKind(data.get("kind", AuthKind.NONE)),
            token_env=data.get("token_env"),
            client_id=data.get("client_id"),
            client_secret_env=data.get("client_secret_env"),
            scopes=tuple(scopes),
            issuer=(data.get("issuer") or "").rstrip("/") or None,
        )


def connector_client_kwargs(definition: "ConnectorDefinition", user) -> dict[str, Any]:
    """The `MCPToolset` keyword arguments that authenticate `user` to the server.

    Raises for a kind not implemented yet: the registry refuses such
    declarations, so reaching that branch is a bug, not an outage.
    """
    auth = definition.auth
    if auth.kind == AuthKind.NONE:
        return {}
    if auth.kind == AuthKind.USER_OAUTH:
        # Imported here: oauth needs the models, which need the app registry.
        # pylint: disable-next=import-outside-toplevel
        from chat.connectors.oauth import UserOAuthHTTPAuth  # noqa: PLC0415

        return {"auth": UserOAuthHTTPAuth(definition, user.pk)}
    raise ConnectorAuthNotSupportedError(f"Connector auth {auth.kind!r} is not implemented yet.")
