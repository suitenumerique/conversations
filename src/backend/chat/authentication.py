"""Custom authentication classes for chat webhooks."""

import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class AiWebhookAuthentication(BaseAuthentication):
    """
    Custom authentication class for AI webhook requests.
    Validates the API key in the Authorization header.
    """

    def authenticate(self, request):
        """
        Authenticate the request and return a two-tuple of (user, token).
        """
        if not settings.STT_WEBHOOK_API_KEY:
            raise AuthenticationFailed("STT_WEBHOOK_API_KEY is not configured.")

        authorization_header: str = request.headers.get("Authorization") or ""
        token = authorization_header.removeprefix("Bearer ")
        if not token or token != settings.STT_WEBHOOK_API_KEY:
            logger.warning(
                "Authentication failed: Bad Authorization header (ip: %s)",
                request.META.get("REMOTE_ADDR"),
            )
            raise AuthenticationFailed()

        # No users are associated with the transcribe webhooks
        return AnonymousUser(), None
