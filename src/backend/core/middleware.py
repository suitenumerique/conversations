"""Custom middleware(s) for the project."""

import json
import logging
from urllib.parse import unquote

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

# We are importing posthog here, but it will only be used if the POSTHOG_KEY is set in settings.
# The settings are checked before any attempt to use posthog.
try:
    import posthog
except ImportError:
    posthog = None


logger = logging.getLogger(__name__)


class PostHogMiddleware:
    """
    This middleware is used to alias the user's distinct_id from the PostHog cookie
    with their email address when they are authenticated. This allows us to track
    users across different sessions and devices.
    """

    def __init__(self, get_response):
        """
        Initialize the middleware and disable it if PostHog is not configured.
        """
        if posthog is None or not settings.POSTHOG_KEY:
            raise MiddlewareNotUsed("POSTHOG_KEY must be set in settings to use PostHogMiddleware.")
        self.get_response = get_response

    def __call__(self, request):
        """
        Process the request to handle the PostHog alias.
        """
        if posthog is not None and settings.POSTHOG_KEY:
            posthog_cookie = request.COOKIES.get(f"ph_{posthog.project_api_key}_posthog")
            if posthog_cookie:
                try:
                    cookie_dict = json.loads(unquote(posthog_cookie))
                    if (
                        cookie_dict.get("distinct_id")
                        and request.user
                        and request.user.is_authenticated
                    ):
                        posthog.alias(cookie_dict["distinct_id"], request.user.email)
                except (json.JSONDecodeError, KeyError):
                    # If the cookie is malformed or doesn't contain the expected
                    # keys, we can't do anything with it, so we ignore it.
                    logger.warning("Malformed PostHog cookie: %s", posthog_cookie)

        response = self.get_response(request)

        return response
