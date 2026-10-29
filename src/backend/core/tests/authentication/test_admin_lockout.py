"""Account-based brute-force protection for the admin password login."""

from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.signals import user_logged_in
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

import pytest
from axes.models import AccessAttempt
from freezegun import freeze_time

from core.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(name="admin_user")
def fixture_admin_user():
    """An administrator using the real password authentication backend."""
    return UserFactory(admin_email="admin@example.com", is_staff=True, is_superuser=True)


def login(client, user, password="password", ip="192.0.2.1"):
    """Submit admin credentials and the form's hidden redirect destination."""
    return client.post(
        reverse("admin:login"),
        {
            "username": user.admin_email,
            "password": password,
            "next": reverse("admin:index"),
        },
        REMOTE_ADDR=ip,
    )


@pytest.mark.parametrize("limit", [2, 5])
def test_admin_locks_account_at_configured_failure_limit(client, admin_user, settings, limit):
    """The threshold locks the account, including correct passwords from other IPs."""
    settings.AXES_FAILURE_LIMIT = limit
    for _ in range(limit - 1):
        assert login(client, admin_user, password="wrong").status_code == 200
    assert login(client, admin_user, password="wrong").status_code == 429
    assert login(client, admin_user, ip="192.0.2.2").status_code == 429
    assert "_auth_user_id" not in client.session

    # The IP is also locked, even when a different account is used.
    other = UserFactory(admin_email="other@example.com", is_staff=True)
    assert login(client, other).status_code == 429
    assert login(client, other, ip="192.0.2.3").status_code == 302
    assert client.session["_auth_user_id"] == str(other.pk)


def test_admin_ip_lockout_counts_failures_across_accounts(client, settings):
    """Password spraying locks the IP even if no account reaches its own limit."""
    settings.AXES_FAILURE_LIMIT = 2
    users = [
        UserFactory(admin_email=f"admin{index}@example.com", is_staff=True) for index in range(3)
    ]
    assert login(client, users[0], password="wrong").status_code == 200
    assert login(client, users[1], password="wrong").status_code == 429
    assert login(client, users[2]).status_code == 429
    assert login(client, users[2], ip="192.0.2.2").status_code == 302


def test_admin_account_lockout_counts_failures_across_ips(client, admin_user, settings):
    """Changing IP addresses does not bypass the account's failure threshold."""
    settings.AXES_FAILURE_LIMIT = 2
    assert login(client, admin_user, password="wrong").status_code == 200
    assert login(client, admin_user, password="wrong", ip="192.0.2.2").status_code == 429
    assert login(client, admin_user, ip="192.0.2.3").status_code == 429


@pytest.mark.parametrize("hours", [0.25, 0.5])
def test_admin_lockout_expires_without_extending_on_blocked_attempts(
    client, admin_user, settings, hours
):
    """The configured cool-off expires even if more attempts occur during lockout."""
    settings.AXES_FAILURE_LIMIT = 1
    settings.AXES_COOLOFF_TIME = hours
    with freeze_time("2026-10-19 12:00:00") as clock:
        assert login(client, admin_user, password="wrong").status_code == 429
        clock.tick(timedelta(hours=hours) - timedelta(seconds=1))
        assert login(client, admin_user).status_code == 429
        clock.tick(timedelta(seconds=2))
        assert login(client, admin_user).status_code == 302


def test_successful_admin_login_resets_previous_failures(client, admin_user, settings):
    """Successful authentication resets the consecutive failure count."""
    settings.AXES_FAILURE_LIMIT = 2
    assert login(client, admin_user, password="wrong").status_code == 200
    assert AccessAttempt.objects.filter(username=admin_user.admin_email).exists()
    response = login(client, admin_user)
    assert response.status_code == 302
    assert response.url == reverse("admin:index")
    assert not AccessAttempt.objects.filter(username=admin_user.admin_email).exists()
    client.logout()
    assert login(client, admin_user, password="wrong").status_code == 200


def test_admin_lockout_can_be_reset_by_management_command(client, admin_user, settings):
    """Operators can unlock an account before the cool-off expires."""
    settings.AXES_FAILURE_LIMIT = 1
    assert login(client, admin_user, password="wrong").status_code == 429
    call_command("axes_reset_username", admin_user.admin_email)
    assert login(client, admin_user).status_code == 302


def test_non_admin_authentication_does_not_record_or_reset_failures(client, admin_user, settings):
    """Other login flows neither use nor clear an administrator's lockout."""
    settings.AXES_FAILURE_LIMIT = 1
    request = RequestFactory().get("/oidc/callback/")
    credentials = {"username": admin_user.admin_email}
    assert authenticate(request, password="wrong", **credentials) is None
    assert not AccessAttempt.objects.exists()

    assert login(client, admin_user, password="wrong").status_code == 429
    assert authenticate(request, password="password", **credentials) == admin_user
    user_logged_in.send(sender=type(admin_user), request=request, user=admin_user)
    assert AccessAttempt.objects.filter(username=admin_user.admin_email).exists()
    assert login(client, admin_user).status_code == 429
