"""Utility functions for OIDC token management."""

from functools import wraps

from django.conf import settings

import requests
from lasuite.oidc_login.backends import get_oidc_refresh_token, store_tokens
from rest_framework.exceptions import AuthenticationFailed


def refresh_access_token(session):
    """Refresh the OIDC access token using the refresh token."""
    response = requests.post(
        settings.OIDC_OP_TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "client_id": settings.OIDC_RP_CLIENT_ID,
            "client_secret": settings.OIDC_RP_CLIENT_SECRET,
            "refresh_token": get_oidc_refresh_token(session),
        },
        timeout=5,
    )
    response.raise_for_status()
    token_info = response.json()

    store_tokens(
        session,
        access_token=token_info.get("access_token"),
        id_token=None,
        refresh_token=token_info.get("refresh_token"),
    )
    return session


def with_fresh_access_token(func):
    """
    Decorator to handle OIDC token refresh and extraction.
    Expects 'session' in kwargs and update it with the fresh token.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        session = kwargs.get("session")
        if session is None:
            raise AuthenticationFailed({"error": "Session is required but not provided"})
        kwargs["session"] = refresh_access_token(session)
        return func(*args, **kwargs)
    return wrapper
