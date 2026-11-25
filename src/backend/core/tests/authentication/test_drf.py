"""Tests for the DRF bearer-token authentication class."""

from django.test.utils import override_settings

import pytest
from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from core.authentication.backends import OIDCAuthenticationBackend
from core.authentication.drf import LoggedOIDCAuthentication

pytestmark = pytest.mark.django_db


@override_settings(OIDC_ALLOWED_EMAIL_DOMAINS=["*.gouv.fr"])
def test_bearer_token_user_denied_by_access_policy_is_forbidden(monkeypatch):
    """A bearer token whose user fails the access policy gets a 403, not a 500."""
    monkeypatch.setattr(
        OIDCAuthenticationBackend,
        "get_userinfo",
        lambda *args: {"sub": "123", "email": "someone@example.com"},
    )
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION="Bearer test-token")

    with pytest.raises(exceptions.PermissionDenied):
        LoggedOIDCAuthentication().authenticate(request)


@override_settings(OIDC_ALLOWED_EMAIL_DOMAINS=["*.gouv.fr"])
def test_bearer_token_user_allowed_by_access_policy_is_authenticated(monkeypatch):
    """A bearer token whose user satisfies the access policy is authenticated."""
    monkeypatch.setattr(
        OIDCAuthenticationBackend,
        "get_userinfo",
        lambda *args: {"sub": "123", "email": "agent@anct.gouv.fr"},
    )
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION="Bearer test-token")

    user, token = LoggedOIDCAuthentication().authenticate(request)

    assert user.email == "agent@anct.gouv.fr"
    assert token == "test-token"
