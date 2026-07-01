"""Middlewares for the core app."""

import re
from logging import getLogger

from django.conf import settings
from django.db import DatabaseError
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

        response = JsonResponse(
            {"code": "maintenance_mode", "detail": "Service under maintenance"},
            status=503,
        )

        # Env-var escape hatch: skip the DB entirely. This path is typically
        # used precisely when the DB is unreachable, so a lookup here would
        # turn the 503 into a 500. No singleton means no ends_at → no
        # Retry-After.
        if settings.MAINTENANCE_MODE:
            return response

        # DB-driven: best-effort Retry-After. Swallow DB errors so a transient
        # failure between the active-check cache hit and this lookup still
        # yields a 503 rather than a 500.
        try:
            ends_at = MaintenanceMode.get_solo().ends_at
        except DatabaseError:
            return response
        if ends_at:
            retry_after = int((ends_at - timezone.now()).total_seconds())
            if retry_after > 0:
                response["Retry-After"] = str(retry_after)
        return response
