"""
Unit tests for the User model
"""

from unittest import mock

from django.core.exceptions import ValidationError

import pytest

from core import factories, models

pytestmark = pytest.mark.django_db


def test_models_users_str():
    """The str representation should be the email."""
    user = factories.UserFactory()
    assert str(user) == user.email


def test_models_users_id_unique():
    """The "id" field should be unique."""
    user = factories.UserFactory()
    with pytest.raises(ValidationError, match="User with this Id already exists."):
        factories.UserFactory(id=user.id)


def test_models_users_send_mail_main_existing():
    """The "email_user' method should send mail to the user's email address."""
    user = factories.UserFactory()

    with mock.patch("django.core.mail.send_mail") as mock_send:
        user.email_user("my subject", "my message")

    mock_send.assert_called_once_with("my subject", "my message", None, [user.email])


def test_models_users_send_mail_main_missing():
    """The "email_user' method should fail if the user has no email address."""
    user = factories.UserFactory(email=None)

    with pytest.raises(ValueError) as excinfo:
        user.email_user("my subject", "my message")

    assert str(excinfo.value) == "User has no email address."


@pytest.mark.parametrize(
    "email, expected",
    [
        ("  John.Doe@Example.COM ", "john.doe@example.com"),
        ("alice@dısk.example", "alice@dısk.example"),
        ("alice@ſmith.example", "alice@ſmith.example"),
        ("alice@\u212aim.example", "alice@\u212aim.example"),
        ("Élodie@Example.com", "Élodie@example.com"),
        ("\talice@example.com\r\n", "alice@example.com"),
        ("alice@example.com\u00a0", "alice@example.com\u00a0"),
        ("\u3000alice@example.com\u3000", "\u3000alice@example.com\u3000"),
        ("", ""),
        (None, None),
    ],
)
def test_models_normalize_email(email, expected):
    """normalize_email should strip and lowercase ASCII letters only."""
    assert models.normalize_email(email) == expected


def test_models_users_email_normalized_on_save():
    """The email of a user should be stored normalized."""
    user = factories.UserFactory(email=" John.Doe@Example.COM ")

    user.refresh_from_db()
    assert user.email == "john.doe@example.com"


def test_models_users_get_user_by_sub_or_email_ascii_case_only(settings):
    """The email fallback should ignore the ASCII case only, never match a lookalike letter."""
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = True
    user = factories.UserFactory(email="alice@disk.example")
    manager = models.User.objects

    assert manager.get_user_by_sub_or_email("unknown-sub", "alice@disk.example") == user
    assert manager.get_user_by_sub_or_email("unknown-sub", " ALICE@DISK.EXAMPLE ") == user
    # dotless i: Postgres UPPER() maps it to "I"
    assert manager.get_user_by_sub_or_email("unknown-sub", "alice@dısk.example") is None
    # long s: Postgres UPPER() maps it to "S"
    assert manager.get_user_by_sub_or_email("unknown-sub", "alice@diſk.example") is None
    # Kelvin sign: Python lower() maps it to "k"
    assert manager.get_user_by_sub_or_email("unknown-sub", "alice@dis\u212a.example") is None
    # Unicode spaces: a bare strip() removes them
    assert manager.get_user_by_sub_or_email("unknown-sub", "alice@disk.example\u3000") is None
    assert manager.get_user_by_sub_or_email("unknown-sub", "\u00a0alice@disk.example") is None


def test_models_users_get_user_by_sub_or_email_duplicate_check_ascii_case_only(settings):
    """Without the email fallback, only an ASCII case variant should be a duplicate email."""
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = False
    settings.OIDC_ALLOW_DUPLICATE_EMAILS = False
    factories.UserFactory(email="alice@disk.example")
    manager = models.User.objects

    assert manager.get_user_by_sub_or_email("unknown-sub", "alice@dısk.example") is None
    with pytest.raises(models.DuplicateEmailError):
        manager.get_user_by_sub_or_email("unknown-sub", "ALICE@disk.example")


@pytest.mark.parametrize("blank_email", ["", " ", "\t\n"])
def test_models_users_get_user_by_sub_or_email_blank_email_matches_nobody(blank_email, settings):
    """A blank email claim should not match the users stored without an email."""
    settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = True
    factories.UserFactory(email="")

    assert models.User.objects.get_user_by_sub_or_email("unknown-sub", blank_email) is None
