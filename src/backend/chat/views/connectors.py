"""Linking a user's account to a connector that authenticates each user.

Browser navigations, not API calls: switching such a connector on sends the
browser to `start`, which sends it to the connector's authorization server,
which sends it back to `callback`, which sends it back to the frontend with
`?connector=<slug>&connector_status=linked|error`. Switching it off goes
through the users API like any other connector (see UserViewSet).
"""

from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_GET

import structlog

from core.analytics import capture_event
from core.feature_flags.helpers import is_feature_enabled

from chat.connectors.oauth import (
    ConnectorOAuthError,
    complete_authorization,
    pop_pending_authorization,
    start_authorization,
)
from chat.connectors.registry import get_connector_definition

logger = structlog.get_logger(__name__)


def _return_to_frontend(slug: str | None, status: str) -> HttpResponseRedirect:
    base = settings.CONNECTORS_OAUTH_RETURN_URL or settings.LOGIN_REDIRECT_URL or "/"
    query = urlencode({"connector": slug or "", "connector_status": status})
    separator = "&" if "?" in base else "?"
    return HttpResponseRedirect(f"{base}{separator}{query}")


def _redirect_uri(request) -> str:
    return settings.CONNECTORS_OAUTH_REDIRECT_URI or request.build_absolute_uri(
        reverse("connector-oauth-callback")
    )


def _linkable(slug: str, user):
    """The definition if `user` may link this connector, else None."""
    definition = get_connector_definition(slug)
    if definition is None or not definition.auth.needs_linking:
        return None
    if definition.feature_flag is not None and not is_feature_enabled(
        user, definition.feature_flag
    ):
        return None
    return definition


@require_GET
def connector_oauth_start(request, slug: str):
    """Send the browser to the connector's authorization server."""
    if not request.user.is_authenticated:
        return _return_to_frontend(slug, "error")
    definition = _linkable(slug, request.user)
    if definition is None:
        return _return_to_frontend(slug, "error")
    try:
        url = start_authorization(definition, request.session, _redirect_uri(request))
    except ConnectorOAuthError as error:
        logger.warning("connector_oauth_start_failed", connector_id=slug, reason=str(error))
        return _return_to_frontend(slug, "error")
    return HttpResponseRedirect(url)


@require_GET
def connector_oauth_callback(request):
    """Finish linking: exchange the code, store the tokens, switch the connector on."""
    if not request.user.is_authenticated:
        return _return_to_frontend(None, "error")
    try:
        pending = pop_pending_authorization(request.session, request.GET.get("state", ""))
    except ConnectorOAuthError as error:
        logger.warning("connector_oauth_callback_refused", reason=str(error))
        return _return_to_frontend(None, "error")

    slug = pending["connector_id"]
    if request.GET.get("error"):
        # The user declined, or the server refused: nothing to store.
        logger.info(
            "connector_oauth_denied", connector_id=slug, error=request.GET.get("error")[:100]
        )
        return _return_to_frontend(slug, "error")

    definition = _linkable(slug, request.user)
    code = request.GET.get("code")
    if definition is None or not code:
        return _return_to_frontend(slug, "error")
    try:
        complete_authorization(request.user, definition, pending, code)
    except ConnectorOAuthError as error:
        logger.warning("connector_oauth_exchange_failed", connector_id=slug, reason=str(error))
        return _return_to_frontend(slug, "error")

    logger.info("connector_linked", connector_id=slug)
    capture_event(
        "connector_toggled",
        request.user.pk,
        properties={"connector_id": slug, "enabled": True},
    )
    return _return_to_frontend(slug, "linked")
