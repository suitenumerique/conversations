"""Utility functions for OIDC token management."""

from django.conf import settings

import requests
from lasuite.oidc_login.backends import get_oidc_refresh_token, store_tokens


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
