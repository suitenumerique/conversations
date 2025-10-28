"""
Asynchronous PostHog context middleware for Django.

Since https://github.com/PostHog/posthog-python/commit/6af129f41413f4f7d55731763ff42e4c0fb66844
The official PostHog Django middleware supports both sync and async requests,
but the call to request.user fails in async contexts.

This is an horrible patch while waiting for an official fix.
Follow https://github.com/PostHog/posthog-python/issues/355
"""

from posthog import contexts
from posthog.integrations.django import PosthogContextMiddleware


class AsyncPosthogContextMiddleware(PosthogContextMiddleware):
    """
    Asynchronous Django middleware to extract PostHog context from HTTP requests.

    While the original PosthogContextMiddleware is supposed to manage both sync and async requests,
    the call to request.user fails in async contexts.
    """

    async def extract_tags_async(self, request):
        """Extract tags from the HTTP request asynchronously."""
        tags = {}

        (user_id, user_email) = await self.extract_request_user_async(request)

        # Extract session ID from X-POSTHOG-SESSION-ID header
        session_id = request.headers.get("X-POSTHOG-SESSION-ID")
        if session_id:
            contexts.set_context_session(session_id)

        # Extract distinct ID from X-POSTHOG-DISTINCT-ID header or request user id
        distinct_id = request.headers.get("X-POSTHOG-DISTINCT-ID") or user_id
        if distinct_id:
            contexts.identify_context(distinct_id)

        # Extract user email
        if user_email:
            tags["email"] = user_email

        # Extract current URL
        absolute_url = request.build_absolute_uri()
        if absolute_url:
            tags["$current_url"] = absolute_url

        # Extract request method
        if request.method:
            tags["$request_method"] = request.method

        # Extract request path
        if request.path:
            tags["$request_path"] = request.path

        # Extract IP address
        ip_address = request.headers.get("X-Forwarded-For")
        if ip_address:
            tags["$ip_address"] = ip_address

        # Extract user agent
        user_agent = request.headers.get("User-Agent")
        if user_agent:
            tags["$user_agent"] = user_agent

        # Apply extra tags if configured
        if self.extra_tags:
            extra = self.extra_tags(request)
            if extra:
                tags.update(extra)

        # Apply tag mapping if configured
        if self.tag_map:
            tags = self.tag_map(tags)

        return tags

    async def extract_request_user_async(self, request):
        """Extract user ID and email from the HTTP request asynchronously."""
        user_id = None
        email = None

        user = await request.auser()

        if user and getattr(user, "is_authenticated", False):
            try:
                user_id = str(user.pk)
            except Exception:  # noqa: BLE001, S110  # pylint: disable=broad-except
                pass

            try:
                email = str(user.email)
            except Exception:  # noqa: BLE001, S110  # pylint: disable=broad-except
                pass

        return user_id, email

    async def __acall__(self, request):
        """
        Asynchronous entry point for async request handling.

        This method is called when the middleware chain is async.
        """
        if self.request_filter and not self.request_filter(request):
            return await self.get_response(request)

        with contexts.new_context(self.capture_exceptions, client=self.client):
            tags = await self.extract_tags_async(request)
            for k, v in tags.items():
                contexts.tag(k, v)

            return await self.get_response(request)
