"""
Tests for the migration normalizing stored user emails
"""

from importlib import import_module

from django.apps import apps

import pytest

from core import factories, models

pytestmark = pytest.mark.django_db

migration = import_module("core.migrations.0016_normalize_stored_user_emails")


def _user_with_stored_email(email, **kwargs):
    """Create a user storing the email as is, like the rows predating the normalization."""
    user = factories.UserFactory(**kwargs)
    models.User.objects.filter(pk=user.pk).update(email=email)
    return user


@pytest.mark.parametrize(
    "stored_email, expected_email",
    [
        ("John.Doe@Example.COM", "john.doe@example.com"),
        ("  john.doe@example.com ", "john.doe@example.com"),
        ("john.doe@example.com", "john.doe@example.com"),
        ("Jane@Dısk.example", "jane@dısk.example"),
        ("Élodie@Example.com", "Élodie@example.com"),
        ("john.doe@example.com\u3000", "john.doe@example.com\u3000"),
        ("", ""),
        (None, None),
    ],
)
def test_migrations_normalize_stored_user_emails(stored_email, expected_email):
    """Only the surrounding spaces and the ASCII case of user emails should change."""
    user = _user_with_stored_email(stored_email)

    migration.forwards(apps, None)

    user.refresh_from_db()
    assert user.email == expected_email


def test_migrations_normalize_stored_user_emails_duplicates_kept():
    """Users whose emails only differ by case should be kept and share the normalized email."""
    upper_user = _user_with_stored_email("John.Doe@example.com")
    lower_user = _user_with_stored_email("john.doe@example.com")

    migration.forwards(apps, None)

    upper_user.refresh_from_db()
    lower_user.refresh_from_db()
    assert upper_user.email == "john.doe@example.com"
    assert lower_user.email == "john.doe@example.com"


def test_migrations_normalize_stored_user_emails_admin_email_ignored():
    """The admin email of a user should not change."""
    user = _user_with_stored_email("john.doe@example.com", admin_email="Admin@Example.com")

    migration.forwards(apps, None)

    user.refresh_from_db()
    assert user.admin_email == "Admin@Example.com"


def test_migrations_normalize_stored_user_emails_several_batches(monkeypatch):
    """Users spread over several batches, the last one partial, should all be normalized."""
    monkeypatch.setattr(migration, "BATCH_SIZE", 2)
    users = [_user_with_stored_email(f"User{i}@Example.com") for i in range(5)]

    migration.forwards(apps, None)

    assert sorted(
        models.User.objects.filter(pk__in=[u.pk for u in users]).values_list("email", flat=True)
    ) == [f"user{i}@example.com" for i in range(5)]
