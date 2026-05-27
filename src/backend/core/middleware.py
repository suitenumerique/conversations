"""Middlewares for the core app."""

import re
from logging import getLogger

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from core.models import MaintenanceMode

logger = getLogger(__name__)


# Paths that must remain reachable while maintenance mode is active.
# Anchored prefixes / exact paths. Static files are handled by WhiteNoiseMiddleware
# upstream, so they never reach this middleware.
_EXEMPT_PATH_RE = re.compile(
    r"^/(?:"
    r"admin(?:/|$)"
    r"|__heartbeat__/?$"
    r"|__lbheartbeat__/?$"
    r"|api/[^/]+/config/?$"
    r")"
)


def is_maintenance_active() -> bool:
    """Whether maintenance mode is currently active.

    OR-combination of the env-var escape hatch and the DB-backed singleton.
    """
    if settings.MAINTENANCE_MODE:
        return True
    return MaintenanceMode.get_solo().is_active_now()


class MaintenanceMiddleware:
    """Short-circuit non-exempt requests with 503 when maintenance is active."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _EXEMPT_PATH_RE.match(request.path) or not is_maintenance_active():
            return self.get_response(request)

        singleton = MaintenanceMode.get_solo()
        response = JsonResponse(
            {"code": "maintenance_mode", "detail": "Service under maintenance"},
            status=503,
        )
        if singleton.ends_at:
            retry_after = int((singleton.ends_at - timezone.now()).total_seconds())
            if retry_after > 0:
                response["Retry-After"] = str(retry_after)
        return response
