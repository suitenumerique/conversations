"""Product event capture towards PostHog."""

import asyncio
import logging

from django.conf import settings

import posthog

logger = logging.getLogger(__name__)


def capture_event(event: str, user_id, properties: dict | None = None) -> None:
    """Send a product event to PostHog, when PostHog is configured.

    `user_id` must be the user's primary key: the frontend identifies people by
    that same value, so browser and backend events land on the same person.

    Properties must stay free of user content (titles, file names, prompts).

    Analytics is never worth failing a request over, so capture errors are
    logged and swallowed.
    """
    if not settings.POSTHOG_KEY:
        return

    try:
        posthog.capture(event, distinct_id=str(user_id), properties=properties)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to capture the PostHog event %s", event)


async def acapture_event(event: str, user_id, properties: dict | None = None) -> None:
    """`capture_event` for async code paths.

    The PostHog client only enqueues onto a background worker, but the streaming
    generators must not call into third-party SDKs directly (same rule as the
    Langfuse calls), so the capture runs off the event loop.
    """
    await asyncio.to_thread(capture_event, event, user_id, properties)
