"""Content-Security-Policy header on backend responses."""

from django.urls import reverse

import pytest

pytestmark = pytest.mark.django_db


def test_api_response_forbids_every_resource(client):
    """API responses are data: nothing may be loaded, framed or submitted from them."""
    response = client.get("/api/v1.0/config/")

    assert response.status_code == 200
    directives = dict(
        directive.strip().split(" ", 1)
        for directive in response.headers["Content-Security-Policy"].split(";")
    )
    assert directives["default-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["form-action"] == "'none'"


def test_admin_is_excluded_from_policy(client):
    """The Django admin needs its own scripts and styles, so it keeps no policy."""
    response = client.get(reverse("admin:login"))

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
