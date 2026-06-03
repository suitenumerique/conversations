"""
Unit tests for the AccessBypassEmail model and its factory
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest

from core import factories, models

pytestmark = pytest.mark.django_db


def test_models_access_bypass_email_factory():
    """The factory should create a valid, persisted, active entry."""
    entry = factories.AccessBypassEmailFactory()

    assert models.AccessBypassEmail.objects.filter(pk=entry.pk).exists()
    assert entry.is_active is True
    assert entry.expires_at > timezone.now()


def test_models_access_bypass_email_str():
    """The str representation should be the email."""
    entry = factories.AccessBypassEmailFactory(email="bypass@example.com")

    assert str(entry) == "bypass@example.com"


def test_models_access_bypass_email_is_normalized_on_save():
    """The email should be stored trimmed and lowercased."""
    entry = factories.AccessBypassEmailFactory(email="  Mixed@Example.COM  ")

    assert entry.email == "mixed@example.com"


def test_models_access_bypass_email_unique():
    """Two entries cannot share the same email."""
    factories.AccessBypassEmailFactory(email="dup@example.com")

    with pytest.raises(ValidationError):
        factories.AccessBypassEmailFactory(email="dup@example.com")


def test_models_access_bypass_email_expires_at_optional():
    """expires_at may be omitted, meaning the bypass never expires."""
    entry = models.AccessBypassEmail.objects.create(email="noexpiry@example.com")

    assert entry.expires_at is None
    assert models.AccessBypassEmail.is_email_allowed("noexpiry@example.com") is True


def test_is_email_allowed_active_not_expired():
    """An active, non-expired entry allows its email."""
    factories.AccessBypassEmailFactory(
        email="ok@example.com",
        expires_at=timezone.now() + timedelta(days=1),
    )

    assert models.AccessBypassEmail.is_email_allowed("ok@example.com") is True


def test_is_email_allowed_is_case_insensitive():
    """Matching ignores casing and surrounding whitespace."""
    factories.AccessBypassEmailFactory(email="ok@example.com")

    assert models.AccessBypassEmail.is_email_allowed("  OK@Example.COM  ") is True


def test_is_email_allowed_inactive():
    """An inactive entry does not allow its email."""
    factories.AccessBypassEmailFactory(email="off@example.com", is_active=False)

    assert models.AccessBypassEmail.is_email_allowed("off@example.com") is False


def test_is_email_allowed_expired():
    """An expired entry does not allow its email."""
    factories.AccessBypassEmailFactory(
        email="old@example.com",
        expires_at=timezone.now() - timedelta(days=1),
    )

    assert models.AccessBypassEmail.is_email_allowed("old@example.com") is False


def test_is_email_allowed_unknown_email():
    """An email with no entry is not allowed."""
    assert models.AccessBypassEmail.is_email_allowed("nobody@example.com") is False


@pytest.mark.parametrize("value", ["", None])
def test_is_email_allowed_empty(value):
    """An empty or missing email is not allowed."""
    assert models.AccessBypassEmail.is_email_allowed(value) is False
