"""Middlewares for the core app."""

import re
import uuid
from logging import getLogger
from secrets import compare_digest

from django.conf import settings
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

import sentry_sdk
import structlog
from django_structlog import signals as structlog_signals
from django_structlog.middlewares import RequestMiddleware
from dockerflow.logging import request_id_context

from core.log_fields import redact_file_stream_key
from core.models import MaintenanceMode

logger = getLogger(__name__)

# Where the Prometheus metrics are served when PROMETHEUS_METRICS_ENABLED is set.
# Defined here rather than next to the view so that this module, which is always
# loaded, does not import prometheus_client when the metrics are disabled.
METRICS_PATH = "/metrics"

# Paths that must remain reachable while maintenance mode is active.
# Anchored prefixes / exact paths. Static files are handled by ServeStaticMiddleware
# upstream, so they never reach this middleware.
_EXEMPT_PATH_RE = re.compile(
    r"^/(?:"
    r"admin(?:/|$)"
    r"|__heartbeat__/?$"
    r"|__lbheartbeat__/?$"
    r"|api/[^/]+/config/?$"
    r"|metrics/?$"
    r")"
)


def is_maintenance_active() -> bool:
    """Whether maintenance mode is currently active.

    OR-combination of the env-var escape hatch and the DB-backed singleton.
    """
    if settings.MAINTENANCE_MODE:
        return True
    return MaintenanceMode.get_solo().is_active_now()


class MaintenanceMiddleware(MiddlewareMixin):
    """Short-circuit non-exempt requests with 503 when maintenance is active.

    Uses MiddlewareMixin so it stays async-capable under ASGI: process_request
    runs in a thread-sensitive executor rather than forcing the whole downstream
    chain through a shielded sync_to_async boundary (which logs spurious
    "CancelledError exception in shielded future" noise on client disconnects).
    """

    def process_request(self, request):
        """Return a 503 for non-exempt requests when maintenance is active."""
        if _EXEMPT_PATH_RE.match(request.path) or not is_maintenance_active():
            return None

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


class PrometheusAuthMiddleware(MiddlewareMixin):
    """Require PROMETHEUS_API_KEY as a bearer token on the metrics endpoint.

    Installed first, and only when PROMETHEUS_METRICS_ENABLED is set. It fails
    closed: with no key configured nothing is served, whatever is presented.
    """

    def process_request(self, request):
        """Refuse a call to the metrics endpoint that does not present the key."""
        if request.path_info.rstrip("/") != METRICS_PATH:
            return None

        api_key = settings.PROMETHEUS_API_KEY
        authorization = request.headers.get("Authorization") or ""
        # compared as bytes: `compare_digest` refuses non-ASCII strings, and
        # what a caller sends in a header is not ours to trust
        if not api_key or not compare_digest(authorization.encode(), f"Bearer {api_key}".encode()):
            response = HttpResponse("Unauthorized", status=401)
            response["WWW-Authenticate"] = 'Bearer realm="metrics"'
            return response

        return None


class RequestLogMiddleware(RequestMiddleware):
    """django-structlog request logs, without the query string: it carries user input."""

    @staticmethod
    def format_request(request):
        """Method and path only (upstream logs get_full_path, ?title=<search> included).

        A file-stream path has its temporary key redacted.
        """
        return f"{request.method} {redact_file_stream_key(request.path)}"


# The shape of an ingress-nginx request id, and of a Langfuse trace id: the
# request id is also the id of a chat turn's Langfuse trace.
REQUEST_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def use_dockerflow_request_id(sender, request, **kwargs):  # pylint: disable=unused-argument
    """Log under the ingress request id DockerflowMiddleware read.

    django-structlog would otherwise generate a second, unrelated one, so the
    logs could not be matched with the ingress access log. Runs before
    `request_started` is logged and before any task is enqueued, so every line
    of the request, and of the Celery tasks it queues, carries this one.

    An id that does not match REQUEST_ID_PATTERN, such as Dockerflow's own
    dashed uuid4 when there is no header, is replaced by a generated one.

    The id is also a tag of the request's Sentry events: under ASGI, an error in
    a streamed response is captured outside the task the log ids are bound in.
    """
    request_id = request_id_context.get(None)
    if not (request_id and REQUEST_ID_PATTERN.fullmatch(request_id)):
        request_id = uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(request_id=request_id)
    sentry_sdk.set_tag("request_id", request_id)


structlog_signals.bind_extra_request_metadata.connect(
    use_dockerflow_request_id, sender=RequestLogMiddleware
)
