"""Per-user OAuth for connectors that need it (`AuthKind.USER_OAUTH`).

Follows the MCP authorization specification, from the client side:

1. Discovery. The connector's server publishes its protected resource
   metadata (RFC 9728), naming its authorization server; that server publishes
   its own metadata (RFC 8414, or OpenID Connect discovery). A declaration may
   name the issuer instead.
2. Linking. Switching the connector on sends the browser to the authorization
   server (authorization code, PKCE S256, `resource` set to the connector's
   URL, RFC 8707). The callback exchanges the code, stores the tokens encrypted
   (`ConnectorCredential`) and records the opt-in. Switching it off deletes
   them and revokes the refresh token, so switching on again links again.
3. Use. During a turn, `UserOAuthHTTPAuth` puts the user's access token on
   every request to the server, refreshes it when it is about to expire, and
   once more when the server answers 401. A refresh the authorization server
   refuses unlinks the connector: the user has to switch it on again.

Tokens never leave this module and the model: they are not logged, not sent
to the frontend and not given to the language model.
"""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

import httpx
import structlog
from asgiref.sync import sync_to_async

from chat.connectors.definition import ConnectorDefinition

logger = structlog.get_logger(__name__)

# Seconds allowed for any call to an authorization server or for discovery.
HTTP_TIMEOUT = 10.0
# Refresh an access token that expires within this many seconds, so it does not
# expire in the middle of a tool call.
REFRESH_MARGIN = 60
# Discovery documents change rarely; refetching them for every turn would put
# two requests in front of each connection.
DISCOVERY_CACHE_TIMEOUT = 60 * 60
# How long an authorization started in the browser may take to come back.
PENDING_AUTHORIZATION_TTL = 10 * 60
# Where pending authorizations are kept in the user's session, by `state`.
SESSION_KEY = "connector_oauth_pending"


class ConnectorOAuthError(Exception):
    """Linking a connector failed: discovery, the authorization or the code exchange."""


class ConnectorTokenRefusedError(ConnectorOAuthError):
    """The authorization server refused a grant: the link is no longer valid."""


class ConnectorNotLinkedError(RuntimeError):
    """A turn needs the user's tokens for a connector and there are none.

    A RuntimeError so that the turn treats it like a server it cannot reach
    (see `chat.connectors.errors`): the connector is dropped, the rest of the
    turn goes on, and a forced connector tells the user it could not be used.
    """


class ConnectorAuthUnavailableError(RuntimeError):
    """The authorization server could not refresh a token during a turn.

    A RuntimeError for the same reason as ConnectorNotLinkedError: the turn
    goes on without the connector. The link is kept; the next turn retries.
    """


@dataclass(frozen=True)
class AuthorizationServer:
    """What we need to know about a connector's authorization server."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str | None
    # The scopes to request: the declaration's, else the resource's own.
    scopes: tuple[str, ...]


# --- Discovery --------------------------------------------------------------


def _well_known_urls(url: str, name: str) -> list[str]:
    """`/.well-known/<name>` for `url`, path-aware first, then at the root."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    urls = [urlunsplit((parts.scheme, parts.netloc, f"/.well-known/{name}{path}", "", ""))]
    if path:
        urls.append(urlunsplit((parts.scheme, parts.netloc, f"/.well-known/{name}", "", "")))
    return urls


def _authorization_server_metadata_urls(issuer: str) -> list[str]:
    """Where an issuer's metadata may be, in the order the MCP specification gives."""
    parts = urlsplit(issuer)
    path = parts.path.rstrip("/")
    root = (parts.scheme, parts.netloc)
    if not path:
        return [
            urlunsplit((*root, "/.well-known/oauth-authorization-server", "", "")),
            urlunsplit((*root, "/.well-known/openid-configuration", "", "")),
        ]
    return [
        urlunsplit((*root, f"/.well-known/oauth-authorization-server{path}", "", "")),
        urlunsplit((*root, f"/.well-known/openid-configuration{path}", "", "")),
        urlunsplit((*root, f"{path}/.well-known/openid-configuration", "", "")),
    ]


def _get_json(url: str) -> dict | None:
    """A JSON object from `url`, or None when there is none there."""
    try:
        response = httpx.get(url, timeout=HTTP_TIMEOUT, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:
        raise ConnectorOAuthError(f"Could not reach {url}: {type(error).__name__}") from error
    if response.status_code != httpx.codes.OK:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _discover(definition: ConnectorDefinition) -> AuthorizationServer:
    auth = definition.auth
    issuer = auth.issuer
    scopes = auth.scopes
    if issuer is None:
        resource = next(
            (
                data
                for url in _well_known_urls(definition.url, "oauth-protected-resource")
                if (data := _get_json(url)) and data.get("authorization_servers")
            ),
            None,
        )
        if resource is None:
            raise ConnectorOAuthError(
                f"Connector {definition.slug!r} publishes no protected resource metadata; "
                "declare its `issuer`."
            )
        issuer = str(resource["authorization_servers"][0]).rstrip("/")
        scopes = scopes or tuple(resource.get("scopes_supported") or ())

    metadata = next(
        (
            data
            for url in _authorization_server_metadata_urls(issuer)
            if (data := _get_json(url)) and str(data.get("issuer", "")).rstrip("/") == issuer
        ),
        None,
    )
    if metadata is None:
        raise ConnectorOAuthError(f"No authorization server metadata for issuer {issuer!r}.")
    if not metadata.get("authorization_endpoint") or not metadata.get("token_endpoint"):
        raise ConnectorOAuthError(f"Issuer {issuer!r} has no authorization or token endpoint.")
    methods = metadata.get("code_challenge_methods_supported")
    if methods is not None and "S256" not in methods:
        raise ConnectorOAuthError(f"Issuer {issuer!r} does not support PKCE S256.")

    return AuthorizationServer(
        issuer=issuer,
        authorization_endpoint=metadata["authorization_endpoint"],
        token_endpoint=metadata["token_endpoint"],
        revocation_endpoint=metadata.get("revocation_endpoint"),
        scopes=tuple(scopes),
    )


def discover(definition: ConnectorDefinition) -> AuthorizationServer:
    """The connector's authorization server, cached. Blocking."""
    key = "connector-oauth-server:" + hashlib.sha256(repr(definition).encode()).hexdigest()
    server = cache.get(key)
    if server is None:
        server = _discover(definition)
        cache.set(key, server, DISCOVERY_CACHE_TIMEOUT)
    return server


# --- Token endpoint ---------------------------------------------------------


@dataclass(frozen=True)
class Tokens:
    """What a token endpoint granted."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scope: str


def _token_request(definition: ConnectorDefinition, form: dict[str, str]) -> Tokens:
    """Call the token endpoint; raise ConnectorTokenRefusedError on a refused grant."""
    server = discover(definition)
    form = {"client_id": definition.auth.client_id, "resource": definition.url, **form}
    if (secret := definition.auth.client_secret) is not None:
        form["client_secret"] = secret
    try:
        response = httpx.post(
            server.token_endpoint,
            data=form,
            timeout=HTTP_TIMEOUT,
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as error:
        raise ConnectorOAuthError(
            f"Could not reach the token endpoint: {type(error).__name__}"
        ) from error

    if response.status_code in (httpx.codes.BAD_REQUEST, httpx.codes.UNAUTHORIZED):
        try:
            reason = response.json().get("error", "")
        except ValueError:
            reason = ""
        raise ConnectorTokenRefusedError(f"Token request refused: {reason or response.status_code}")
    if response.status_code != httpx.codes.OK:
        raise ConnectorOAuthError(f"Token endpoint answered {response.status_code}.")

    try:
        data = response.json()
    except ValueError as error:
        raise ConnectorOAuthError("Token endpoint answered with no JSON.") from error
    if not data.get("access_token") or str(data.get("token_type", "")).lower() != "bearer":
        raise ConnectorOAuthError("Token endpoint answered with no bearer token.")

    expires_in = data.get("expires_in")
    return Tokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=(
            timezone.now() + timedelta(seconds=int(expires_in))
            if isinstance(expires_in, int | float) or str(expires_in or "").isdigit()
            else None
        ),
        scope=str(data.get("scope", "")),
    )


def _revoke(definition: ConnectorDefinition, token: str) -> None:
    """Revoke a refresh token, best effort: the link is gone on our side anyway."""
    try:
        server = discover(definition)
        if not server.revocation_endpoint:
            return
        form = {
            "token": token,
            "token_type_hint": "refresh_token",
            "client_id": definition.auth.client_id,
        }
        if (secret := definition.auth.client_secret) is not None:
            form["client_secret"] = secret
        httpx.post(server.revocation_endpoint, data=form, timeout=HTTP_TIMEOUT)
    except (ConnectorOAuthError, httpx.HTTPError) as error:
        logger.warning(
            "connector_token_revocation_failed",
            connector_id=definition.slug,
            error_type=type(error).__name__,
        )


# --- Linking ----------------------------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _pending(session) -> dict:
    """The session's pending authorizations, without the expired ones."""
    now = time.time()
    return {
        state: pending
        for state, pending in (session.get(SESSION_KEY) or {}).items()
        if now - pending.get("created", 0) < PENDING_AUTHORIZATION_TTL
    }


def start_authorization(definition: ConnectorDefinition, session, redirect_uri: str) -> str:
    """The URL to send the browser to, to link the user's account. Blocking.

    The PKCE verifier and the redirect URI stay in the session under a random
    `state`, which the callback must bring back.
    """
    server = discover(definition)
    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()

    pending = _pending(session)
    pending[state] = {
        "connector_id": definition.slug,
        "verifier": verifier,
        "redirect_uri": redirect_uri,
        "created": time.time(),
    }
    session[SESSION_KEY] = pending

    params = {
        "response_type": "code",
        "client_id": definition.auth.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": definition.url,
    }
    if server.scopes:
        params["scope"] = " ".join(server.scopes)
    separator = "&" if "?" in server.authorization_endpoint else "?"
    return f"{server.authorization_endpoint}{separator}{urlencode(params)}"


def pop_pending_authorization(session, state: str) -> dict:
    """The pending authorization `state` names, removed from the session."""
    pending = _pending(session)
    entry = pending.pop(state, None) if state else None
    session[SESSION_KEY] = pending
    if entry is None:
        raise ConnectorOAuthError("Unknown or expired authorization state.")
    return entry


def complete_authorization(user, definition: ConnectorDefinition, pending: dict, code: str):
    """Exchange the code, store the tokens and record the opt-in. Blocking."""
    tokens = _token_request(
        definition,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending["redirect_uri"],
            "code_verifier": pending["verifier"],
        },
    )
    # pylint: disable-next=import-outside-toplevel
    from chat.models import ConnectorCredential  # noqa: PLC0415

    with transaction.atomic():
        credential = (
            ConnectorCredential.objects.select_for_update()
            .filter(user=user, connector_id=definition.slug)
            .first()
        ) or ConnectorCredential(user=user, connector_id=definition.slug)
        _store(credential, tokens)
        _set_opt_in(user, definition.slug, enabled=True)


def unlink(user, definition: ConnectorDefinition, *, revoke: bool = True) -> None:
    """Forget the user's tokens for the connector and switch it off. Blocking."""
    # pylint: disable-next=import-outside-toplevel
    from chat.models import ConnectorCredential  # noqa: PLC0415

    with transaction.atomic():
        credential = (
            ConnectorCredential.objects.select_for_update()
            .filter(user=user, connector_id=definition.slug)
            .first()
        )
        refresh_token = credential.refresh_token if credential else None
        if credential is not None:
            credential.delete()
        _set_opt_in(user, definition.slug, enabled=False)
    if revoke and refresh_token:
        _revoke(definition, refresh_token)


def _store(credential, tokens: Tokens) -> None:
    credential.access_token = tokens.access_token
    # A refresh may come back without a new refresh token: keep the old one.
    if tokens.refresh_token:
        credential.refresh_token = tokens.refresh_token
    credential.expires_at = tokens.expires_at
    credential.scope = tokens.scope or credential.scope
    credential.save()


def _set_opt_in(user, slug: str, *, enabled: bool) -> None:
    # Re-read under lock: the user object in hand may be stale.
    user = get_user_model().objects.select_for_update().get(pk=user.pk)
    allowed = [s for s in (user.allowed_connectors or []) if s != slug]
    if enabled:
        allowed.append(slug)
    if allowed != (user.allowed_connectors or []):
        user.allowed_connectors = allowed
        user.save(update_fields=["allowed_connectors", "updated_at"])


# --- Use during a turn ------------------------------------------------------


@dataclass(frozen=True)
class AccessToken:
    """A usable access token and until when we may use it without asking."""

    value: str
    expires_at: datetime | None

    def fresh(self) -> bool:
        """Whether it is still usable without a refresh."""
        return self.expires_at is None or self.expires_at > timezone.now() + timedelta(
            seconds=REFRESH_MARGIN
        )


def get_access_token(
    user_id, definition: ConnectorDefinition, *, rejected: str | None = None
) -> AccessToken | None:
    """The user's access token for the connector, refreshed if needed. Blocking.

    `rejected` is a token the server just refused: refresh unless another
    request already did. None means the user has no usable link any more —
    never linked, or the refresh was refused, which unlinks the connector.

    The credential row is locked while refreshing, so concurrent requests do
    not spend a single-use refresh token twice.
    """
    # pylint: disable-next=import-outside-toplevel
    from chat.models import ConnectorCredential  # noqa: PLC0415

    with transaction.atomic():
        credential = (
            ConnectorCredential.objects.select_for_update()
            .select_related("user")
            .filter(user_id=user_id, connector_id=definition.slug)
            .first()
        )
        if credential is None:
            return None
        current = credential.access_token
        stale = current == rejected or credential.expires_within(REFRESH_MARGIN)
        if not stale:
            return AccessToken(current, credential.expires_at)

        refresh_token = credential.refresh_token
        if not refresh_token:
            if current == rejected or credential.expires_within(0):
                credential.delete()
                _set_opt_in(credential.user, definition.slug, enabled=False)
                logger.info("connector_unlinked_expired", connector_id=definition.slug)
                return None
            return AccessToken(current, credential.expires_at)

        try:
            tokens = _token_request(
                definition, {"grant_type": "refresh_token", "refresh_token": refresh_token}
            )
        except ConnectorTokenRefusedError:
            credential.delete()
            _set_opt_in(credential.user, definition.slug, enabled=False)
            logger.info("connector_unlinked_refresh_refused", connector_id=definition.slug)
            return None
        _store(credential, tokens)
        return AccessToken(tokens.access_token, tokens.expires_at)


class UserOAuthHTTPAuth(httpx.Auth):
    """Puts the user's access token on every request to the connector's server.

    Keeps the token between requests of the same turn, refreshes it before it
    expires, and once more if the server answers 401. Raises
    ConnectorNotLinkedError when the user has no usable link.
    """

    def __init__(self, definition: ConnectorDefinition, user_id):
        self.definition = definition
        self.user_id = user_id
        self._token: AccessToken | None = None

    async def _token_for(self, rejected: str | None = None) -> str:
        if rejected is None and self._token is not None and self._token.fresh():
            return self._token.value
        try:
            self._token = await sync_to_async(get_access_token)(
                self.user_id, self.definition, rejected=rejected
            )
        except ConnectorOAuthError as error:
            logger.warning(
                "connector_token_refresh_failed",
                connector_id=self.definition.slug,
                reason=str(error),
            )
            raise ConnectorAuthUnavailableError(
                f"Could not refresh the token for connector {self.definition.slug!r}."
            ) from error
        if self._token is None:
            raise ConnectorNotLinkedError(
                f"No usable link to connector {self.definition.slug!r} for this user."
            )
        return self._token.value

    async def async_auth_flow(self, request):
        token = await self._token_for()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == httpx.codes.UNAUTHORIZED:
            token = await self._token_for(rejected=token)
            request.headers["Authorization"] = f"Bearer {token}"
            yield request

    def sync_auth_flow(self, request):
        raise RuntimeError("UserOAuthHTTPAuth only works with an async client.")
