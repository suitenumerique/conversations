"""DRF authentication classes."""

import structlog
from mozilla_django_oidc.contrib.drf import OIDCAuthentication


class LoggedOIDCAuthentication(OIDCAuthentication):
    """OIDC bearer-token authentication that binds the user to the log context.

    RequestLogMiddleware binds `user_id` from Django's session user, before DRF
    authenticates a bearer token: without this, the view's lines (and the Celery
    tasks it queues) would log `user_id: null` for a bearer-authenticated user.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            structlog.contextvars.bind_contextvars(user_id=str(result[0].pk))
        return result
