"""Unit tests for the authentication callback view."""

from django.http import HttpResponseRedirect
from django.test.utils import override_settings

from core.authentication import views
from core.authentication.backends import OIDCRoleAccessDenied
from core.authentication.views import OIDCAuthenticationCallbackView


@override_settings(LOGIN_REDIRECT_URL_FAILURE="https://example.com")
def test_callback_redirects_denied_user_to_unauthorized_page(rf, monkeypatch):
    """A role-denied user is redirected to the frontend access-denied page.

    The target keeps its trailing slash so links minted before the frontend
    became a single-page app keep resolving to the same URL.
    """

    def raise_denied(self, request):  # pylint: disable=unused-argument
        raise OIDCRoleAccessDenied("denied")

    monkeypatch.setattr(views.LaSuiteOIDCAuthenticationCallbackView, "get", raise_denied)

    view = OIDCAuthenticationCallbackView()
    request = rf.get("/oidc/callback/")
    request.session = {}
    view.request = request

    response = view.get(request)

    assert isinstance(response, HttpResponseRedirect)
    assert response.status_code == 302
    assert response.url == "https://example.com/unauthorized/"
