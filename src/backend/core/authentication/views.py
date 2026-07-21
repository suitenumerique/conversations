"""Authentication views for the Conversations core app."""

from django.http import HttpResponseRedirect

from lasuite.oidc_login.views import (
    OIDCAuthenticationCallbackView as LaSuiteOIDCAuthenticationCallbackView,
)

from core.authentication.backends import OIDCRoleAccessDenied

# Frontend path shown to users whose account is not allowed to access the app.
# The frontend is a client-routed single-page app: nginx serves index.html for
# this path and the router renders the access-denied page. The trailing slash is
# kept so links minted before the SPA migration keep resolving to the same URL.
ACCESS_DENIED_PATH = "/unauthorized/"


class OIDCAuthenticationCallbackView(LaSuiteOIDCAuthenticationCallbackView):
    """Callback view that turns a role-based access denial into a friendly redirect.

    When the backend rejects a user for lacking a required role, the resulting
    exception bubbles up through the auth flow (it would otherwise surface as a
    raw 400). We intercept it here and redirect to the frontend access-denied
    page, instead of the default failure URL which is the app root and would
    bounce the user straight back into the login loop.
    """

    def get(self, request):
        """Handle the OIDC callback, redirecting denied users to the access-denied page."""
        try:
            return super().get(request)
        except OIDCRoleAccessDenied:
            return HttpResponseRedirect(f"{self.failure_url.rstrip('/')}{ACCESS_DENIED_PATH}")
