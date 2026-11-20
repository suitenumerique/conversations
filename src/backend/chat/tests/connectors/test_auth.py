"""The authentication seam: how a declaration says a connector authenticates."""

from types import SimpleNamespace

import pytest

from chat.connectors.auth import (
    AuthKind,
    ConnectorAuth,
    ConnectorAuthNotSupportedError,
    connector_client_kwargs,
)


def test_anonymous_is_the_default_and_adds_nothing_to_the_client():
    """A public server is called with no credentials at all."""
    auth = ConnectorAuth()

    assert auth.kind is AuthKind.NONE
    assert auth.supported is True
    assert not connector_client_kwargs(SimpleNamespace(auth=auth), user=None)


def test_a_deployment_token_is_named_but_not_supported():
    """Declared, so the data model is ready; refused, so nothing goes out anonymously."""
    auth = ConnectorAuth(kind=AuthKind.DEPLOYMENT_TOKEN, token_env="FOO_TOKEN")
    assert auth.supported is False
    with pytest.raises(ConnectorAuthNotSupportedError):
        connector_client_kwargs(SimpleNamespace(auth=auth), user=None)


def test_user_oauth_puts_the_users_token_on_requests():
    """Supported: the toolset gets an httpx auth bound to the user and connector."""
    # pylint: disable-next=import-outside-toplevel
    from chat.connectors.oauth import UserOAuthHTTPAuth  # noqa: PLC0415

    auth = ConnectorAuth(kind=AuthKind.USER_OAUTH, client_id="conversations")
    definition = SimpleNamespace(auth=auth, slug="sofia")
    assert auth.supported is True
    assert auth.needs_linking is True

    kwargs = connector_client_kwargs(definition, user=SimpleNamespace(pk=42))

    assert isinstance(kwargs["auth"], UserOAuthHTTPAuth)
    assert kwargs["auth"].user_id == 42


def test_a_user_oauth_declaration_reads_back():
    """Client, secret variable, scopes and issuer; a trailing slash is dropped."""
    assert ConnectorAuth.from_dict(
        {
            "kind": "user_oauth",
            "client_id": "conversations",
            "client_secret_env": "SECRET",
            "scopes": ["openid", "profile"],
            "issuer": "https://sso.example.org/realms/r/",
        }
    ) == ConnectorAuth(
        kind=AuthKind.USER_OAUTH,
        client_id="conversations",
        client_secret_env="SECRET",
        scopes=("openid", "profile"),
        issuer="https://sso.example.org/realms/r",
    )


def test_a_deployment_token_must_say_where_its_secret_lives():
    """The secret is read from the environment, never from the declaration."""
    with pytest.raises(ValueError, match="token_env"):
        ConnectorAuth(kind=AuthKind.DEPLOYMENT_TOKEN)


def test_token_env_only_belongs_to_a_deployment_token():
    """A stray token_env on another kind is a mistake worth catching."""
    with pytest.raises(ValueError, match="token_env"):
        ConnectorAuth(kind=AuthKind.NONE, token_env="FOO_TOKEN")


def test_a_declaration_reads_back():
    """The `auth` object of an MCP_CONNECTORS entry."""
    assert ConnectorAuth.from_dict(None) == ConnectorAuth()
    assert ConnectorAuth.from_dict(
        {"kind": "deployment_token", "token_env": "FOO_TOKEN"}
    ) == ConnectorAuth(kind=AuthKind.DEPLOYMENT_TOKEN, token_env="FOO_TOKEN")
    with pytest.raises(ValueError):
        ConnectorAuth.from_dict({"kind": "magic"})
    with pytest.raises(ValueError, match="Unknown"):
        ConnectorAuth.from_dict({"kind": "none", "secret": "s3cr3t"})
