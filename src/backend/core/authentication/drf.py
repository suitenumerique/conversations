"""DRF authentication classes."""

import structlog
from mozilla_django_oidc.contrib.drf import OIDCAuthentication
from rest_framework import exceptions

from core.authentication.backends import OIDCRoleAccessDenied


class LoggedOIDCAuthentication(OIDCAuthentication):
    """OIDC bearer-token authentication that binds the user to the log context.

    RequestLogMiddleware binds `user_id` from Django's session user, before DRF
    authenticates a bearer token: without this, the view's lines (and the Celery
    tasks it queues) would log `user_id: null` for a bearer-authenticated user.

    A token whose user fails the access policy (role or email domain) is turned
    into a 403: the parent class only handles HTTP and SuspiciousOperation
    errors, so the backend's OIDCRoleAccessDenied would otherwise be a 500.
    """

    def authenticate(self, request):
        try:
            result = super().authenticate(request)
        except OIDCRoleAccessDenied as exc:
            raise exceptions.PermissionDenied(
                "User does not satisfy the application access policy."
            ) from exc
        if result is not None:
            structlog.contextvars.bind_contextvars(user_id=str(result[0].pk))
        return result
