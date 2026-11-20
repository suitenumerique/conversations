"""Per-user OAuth connectors: discovery, linking, token refresh and use."""

import base64
import hashlib
from contextlib import AsyncExitStack
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.core.cache import cache
from django.utils import timezone

import httpx
import pytest
import respx
from asgiref.sync import sync_to_async
from cryptography.fernet import Fernet
from rest_framework.test import APIClient

from core.factories import UserFactory

from chat.connectors.definition import ConnectorDefinition
from chat.connectors.errors import is_connector_unreachable
from chat.connectors.oauth import (
    SESSION_KEY,
    ConnectorAuthUnavailableError,
    ConnectorNotLinkedError,
    ConnectorOAuthError,
    UserOAuthHTTPAuth,
    get_access_token,
)
from chat.connectors.registry import get_connector_definition, validate_connector_declarations
from chat.connectors.turn import TurnConnectors
from chat.models import ConnectorCredential

pytestmark = pytest.mark.django_db

MCP_URL = "https://mcp.example.org/mcp"
ISSUER = "https://sso.example.org/auth/realms/master"
AUTHORIZE = f"{ISSUER}/protocol/openid-connect/auth"
TOKEN = f"{ISSUER}/protocol/openid-connect/token"
REVOKE = f"{ISSUER}/protocol/openid-connect/revoke"


def _declaration(**auth):
    return {
        "slug": "sofia",
        "name": "SofIA",
        "url": MCP_URL,
        "instructions": "Use SofIA for the ecological transition.",
        "auth": {"kind": "user_oauth", "client_id": "conversations", **auth},
    }


@pytest.fixture(autouse=True)
def _oauth_connector(settings):
    """One per-user OAuth connector, with the encryption key it needs."""
    settings.DATAGOUV_CONNECTOR_URL = ""
    settings.MCP_CONNECTORS = [_declaration()]
    settings.CONNECTORS_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.CONNECTORS_OAUTH_REDIRECT_URI = None
    settings.CONNECTORS_OAUTH_RETURN_URL = "https://app.example.org/"
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(name="servers")
def fixture_servers():
    """The connector's resource metadata and a Keycloak-like authorization server."""
    with respx.mock(assert_all_called=False) as router:
        router.get("https://mcp.example.org/.well-known/oauth-protected-resource/mcp").respond(
            json={
                "resource": MCP_URL,
                "authorization_servers": [ISSUER],
                "scopes_supported": ["openid"],
            }
        )
        router.get(
            "https://sso.example.org/.well-known/oauth-authorization-server/auth/realms/master"
        ).respond(404)
        router.get(
            "https://sso.example.org/.well-known/openid-configuration/auth/realms/master"
        ).respond(404)
        router.get(f"{ISSUER}/.well-known/openid-configuration").respond(
            json={
                "issuer": ISSUER,
                "authorization_endpoint": AUTHORIZE,
                "token_endpoint": TOKEN,
                "revocation_endpoint": REVOKE,
                "code_challenge_methods_supported": ["plain", "S256"],
            }
        )
        yield router


def _credential(user, *, expires_in=300, refresh="refresh-1", access="access-1"):
    credential = ConnectorCredential(user=user, connector_id="sofia")
    credential.access_token = access
    credential.refresh_token = refresh
    credential.expires_at = timezone.now() + timedelta(seconds=expires_in)
    credential.save()
    user.allowed_connectors = ["sofia"]
    user.save()
    return credential


# --- Declaration ------------------------------------------------------------


def test_user_oauth_declaration_is_accepted():
    """A user_oauth connector with a client and a key is offered."""
    assert not validate_connector_declarations()
    definition = get_connector_definition("sofia")
    assert definition.auth.needs_linking
    assert definition.auth.client_id == "conversations"


@pytest.mark.parametrize(
    "auth",
    [
        {"kind": "user_oauth"},
        {"kind": "user_oauth", "client_id": "c", "token_env": "X"},
        {"kind": "user_oauth", "client_id": "c", "scopes": "openid"},
        {"kind": "none", "client_id": "c"},
    ],
)
def test_invalid_oauth_declarations_are_refused(settings, auth):
    """A client is required, and fields of other kinds do not belong."""
    settings.MCP_CONNECTORS = [_declaration() | {"auth": auth}]
    assert validate_connector_declarations()
    assert get_connector_definition("sofia") is None


def test_user_oauth_needs_the_encryption_key(settings):
    """Tokens are never stored in clear: no key, no connector."""
    settings.CONNECTORS_TOKEN_ENCRYPTION_KEY = None
    errors = validate_connector_declarations()
    assert any("CONNECTORS_TOKEN_ENCRYPTION_KEY" in error for error in errors)


def test_client_secret_must_be_in_the_environment(settings, monkeypatch):
    """A confidential client names its secret's variable, which must be set."""
    settings.MCP_CONNECTORS = [_declaration(client_secret_env="SOFIA_SECRET")]
    monkeypatch.delenv("SOFIA_SECRET", raising=False)
    assert any("SOFIA_SECRET" in error for error in validate_connector_declarations())

    monkeypatch.setenv("SOFIA_SECRET", "s3cret")
    assert not validate_connector_declarations()
    assert get_connector_definition("sofia").auth.client_secret == "s3cret"


def test_config_tells_the_frontend_how_a_connector_authenticates():
    """The frontend needs to know switching it on means authorizing it."""
    response = APIClient().get("/api/v1.0/config/")
    assert response.json()["CONNECTORS"][0]["auth"] == "user_oauth"


# --- Linking ----------------------------------------------------------------


def _start(client):
    response = client.get("/api/v1.0/connectors/sofia/oauth/start/")
    assert response.status_code == 302
    return urlsplit(response["Location"]), parse_qs(urlsplit(response["Location"]).query)


def test_start_sends_the_browser_to_the_discovered_authorization_server(servers):
    """PKCE S256, the connector as `resource`, the advertised scope, a fresh state."""
    del servers
    user = UserFactory()
    client = APIClient()
    client.force_login(user)

    location, params = _start(client)

    assert f"{location.scheme}://{location.netloc}{location.path}" == AUTHORIZE
    assert params["client_id"] == ["conversations"]
    assert params["response_type"] == ["code"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["resource"] == [MCP_URL]
    assert params["scope"] == ["openid"]
    assert params["redirect_uri"] == ["http://testserver/api/v1.0/connectors/oauth/callback/"]
    pending = client.session[SESSION_KEY][params["state"][0]]
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert params["code_challenge"] == [expected]


def test_start_requires_a_signed_in_user():
    """Anonymous visitors are sent back with an error, never to the server."""
    response = APIClient().get("/api/v1.0/connectors/sofia/oauth/start/")
    assert response.status_code == 302
    assert "connector_status=error" in response["Location"]


def test_start_refuses_a_connector_without_per_user_auth(settings, servers):
    """Only user_oauth connectors are linked."""
    del servers
    settings.MCP_CONNECTORS = [_declaration() | {"auth": {"kind": "none"}}]
    client = APIClient()
    client.force_login(UserFactory())
    response = client.get("/api/v1.0/connectors/sofia/oauth/start/")
    assert "connector_status=error" in response["Location"]


def test_callback_stores_encrypted_tokens_and_switches_the_connector_on(servers):
    """The code is exchanged with its verifier; the tokens are kept, encrypted."""
    token_route = servers.post(TOKEN).respond(
        json={
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": "openid",
        }
    )
    user = UserFactory(allowed_connectors=[])
    client = APIClient()
    client.force_login(user)
    _, params = _start(client)
    state = params["state"][0]
    verifier = client.session[SESSION_KEY][state]["verifier"]

    response = client.get(
        "/api/v1.0/connectors/oauth/callback/", {"state": state, "code": "the-code"}
    )

    assert response["Location"] == (
        "https://app.example.org/?connector=sofia&connector_status=linked"
    )
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["the-code"]
    assert form["code_verifier"] == [verifier]
    assert form["client_id"] == ["conversations"]
    assert form["resource"] == [MCP_URL]

    credential = ConnectorCredential.objects.get(user=user, connector_id="sofia")
    assert credential.access_token == "access-1"
    assert credential.refresh_token == "refresh-1"
    assert "access-1" not in credential.encrypted_access_token
    user.refresh_from_db()
    assert user.allowed_connectors == ["sofia"]
    # The state is single use.
    replay = client.get("/api/v1.0/connectors/oauth/callback/", {"state": state, "code": "x"})
    assert "connector_status=error" in replay["Location"]


def test_callback_refuses_an_unknown_state(servers):
    """A state this session did not start is refused before any exchange."""
    token_route = servers.post(TOKEN).respond(json={})
    client = APIClient()
    client.force_login(UserFactory())
    response = client.get("/api/v1.0/connectors/oauth/callback/", {"state": "forged", "code": "c"})
    assert "connector_status=error" in response["Location"]
    assert not token_route.called


def test_callback_when_the_user_declines(servers):
    """The server's error comes back; nothing is stored."""
    user = UserFactory()
    client = APIClient()
    client.force_login(user)
    _, params = _start(client)
    del servers

    response = client.get(
        "/api/v1.0/connectors/oauth/callback/",
        {"state": params["state"][0], "error": "access_denied"},
    )
    assert response["Location"].endswith("connector=sofia&connector_status=error")
    assert not ConnectorCredential.objects.exists()


def test_callback_when_the_exchange_is_refused(servers):
    """A refused code is an error for the user, and nothing is stored."""
    servers.post(TOKEN).respond(400, json={"error": "invalid_grant"})
    client = APIClient()
    client.force_login(UserFactory())
    _, params = _start(client)
    response = client.get(
        "/api/v1.0/connectors/oauth/callback/", {"state": params["state"][0], "code": "c"}
    )
    assert "connector_status=error" in response["Location"]
    assert not ConnectorCredential.objects.exists()


# --- Users API --------------------------------------------------------------


def test_api_cannot_switch_on_an_unlinked_oauth_connector():
    """Switching it on goes through the authorization, never the field alone."""
    user = UserFactory(allowed_connectors=[])
    client = APIClient()
    client.force_login(user)
    response = client.patch(
        f"/api/v1.0/users/{user.id!s}/", {"allowed_connectors": ["sofia"]}, format="json"
    )
    assert response.status_code == 400
    assert "Link your account" in str(response.json())


def test_api_switching_off_forgets_and_revokes_the_tokens(servers):
    """So that switching it on again authorizes again."""
    revoke_route = servers.post(REVOKE).respond(200)
    user = UserFactory()
    _credential(user)
    client = APIClient()
    client.force_login(user)

    response = client.patch(
        f"/api/v1.0/users/{user.id!s}/", {"allowed_connectors": []}, format="json"
    )

    assert response.status_code == 200
    assert not ConnectorCredential.objects.filter(user=user).exists()
    assert parse_qs(revoke_route.calls.last.request.content.decode())["token"] == ["refresh-1"]


# --- Tokens during a turn ---------------------------------------------------


def test_a_fresh_token_is_used_as_is(servers):
    """No request to the authorization server while the token is valid."""
    token_route = servers.post(TOKEN)
    user = UserFactory()
    _credential(user, expires_in=600)

    token = get_access_token(user.pk, get_connector_definition("sofia"))

    assert token.value == "access-1"
    assert not token_route.called


def test_an_expiring_token_is_refreshed_and_the_new_one_kept(servers):
    """Refreshed ahead of expiry; a rotated refresh token replaces the old one."""
    token_route = servers.post(TOKEN).respond(
        json={
            "access_token": "access-2",
            "refresh_token": "refresh-2",
            "token_type": "bearer",
            "expires_in": 300,
        }
    )
    user = UserFactory()
    credential = _credential(user, expires_in=10)

    token = get_access_token(user.pk, get_connector_definition("sofia"))

    assert token.value == "access-2"
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form["grant_type"] == ["refresh_token"]
    assert form["refresh_token"] == ["refresh-1"]
    credential.refresh_from_db()
    assert credential.access_token == "access-2"
    assert credential.refresh_token == "refresh-2"


def test_a_refused_refresh_unlinks_the_connector(servers):
    """The user has to authorize again: the connector is switched off."""
    servers.post(TOKEN).respond(400, json={"error": "invalid_grant"})
    user = UserFactory()
    _credential(user, expires_in=-10)

    assert get_access_token(user.pk, get_connector_definition("sofia")) is None

    assert not ConnectorCredential.objects.filter(user=user).exists()
    user.refresh_from_db()
    assert user.allowed_connectors == []


def test_an_unreachable_authorization_server_is_an_outage_not_an_unlink(servers):
    """A server down for a moment must not cost the user their link."""
    servers.post(TOKEN).mock(side_effect=httpx.ConnectError("down"))
    user = UserFactory()
    _credential(user, expires_in=-10)

    with pytest.raises(ConnectorOAuthError):
        get_access_token(user.pk, get_connector_definition("sofia"))
    assert ConnectorCredential.objects.filter(user=user).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_http_auth_when_the_authorization_server_is_down(servers):
    """Reads as an outage, so the turn drops the connector rather than failing."""
    servers.post(TOKEN).mock(side_effect=httpx.ConnectError("down"))
    user = await sync_to_async(UserFactory)()
    await sync_to_async(_credential)(user, expires_in=-10)
    definition = await _definition()

    async with httpx.AsyncClient(auth=UserOAuthHTTPAuth(definition, user.pk)) as client:
        with pytest.raises(ConnectorAuthUnavailableError) as raised:
            await client.post(MCP_URL, json={})
    assert is_connector_unreachable(raised.value)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_http_auth_sends_the_token_and_retries_once_after_a_401(servers):
    """A token the server refuses is refreshed once, then the request replayed."""
    servers.post(TOKEN).respond(
        json={"access_token": "access-2", "token_type": "Bearer", "expires_in": 300}
    )
    mcp_route = servers.post(MCP_URL).mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"ok": True})]
    )
    user = await sync_to_async(UserFactory)()
    await sync_to_async(_credential)(user, expires_in=600)
    definition = await _definition()

    async with httpx.AsyncClient(auth=UserOAuthHTTPAuth(definition, user.pk)) as client:
        response = await client.post(MCP_URL, json={})

    assert response.status_code == 200
    headers = [call.request.headers["Authorization"] for call in mcp_route.calls]
    assert headers == ["Bearer access-1", "Bearer access-2"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_http_auth_without_a_link_is_an_outage(servers):
    """No tokens: the connector is dropped from the turn like an unreachable one."""
    del servers
    user = await sync_to_async(UserFactory)()
    definition = await _definition()

    async with httpx.AsyncClient(auth=UserOAuthHTTPAuth(definition, user.pk)) as client:
        with pytest.raises(ConnectorNotLinkedError):
            await client.post(MCP_URL, json={})


async def _definition() -> ConnectorDefinition:
    return await sync_to_async(get_connector_definition)("sofia")


def test_turn_offers_an_oauth_connector_only_once_linked():
    """Opted in without a link — say, the link was dropped — is not available."""
    user = UserFactory(allowed_connectors=["sofia"])
    connector = TurnConnectors.for_user(user, uuid4()).get("sofia")
    assert not connector.linked
    assert not connector.available
    assert connector.toolsets() == []

    _credential(user)
    connector = TurnConnectors.for_user(user, uuid4()).get("sofia")
    assert connector.available
    assert len(connector.toolsets()) == 1


@pytest.mark.asyncio
async def test_forcing_an_unlinked_oauth_connector_reports_it_absent():
    """The model is told it could not be used, and so is the user."""

    user = await sync_to_async(UserFactory)(allowed_connectors=[])
    connectors = await sync_to_async(TurnConnectors.for_user)(user, uuid4())
    connectors.force(["sofia"])

    async with AsyncExitStack() as stack:
        connected = await connectors.enter(stack)

    assert connected.toolsets == []
    assert [(c.connector_id, ok) for c, ok in connected.forced] == [("sofia", False)]
    assert "could not be reached" in connectors.unreachable_forced_instructions()
