"""Strength rules applied to admin passwords."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

import pytest

from core.factories import UserFactory


@pytest.mark.parametrize(
    "password",
    [
        "Sh0rt-pass",  # under 12 characters
        "123456789012345",  # only digits
        "password1234",  # common password
    ],
)
def test_weak_password_is_rejected(password):
    """Short, numeric and common passwords are refused."""
    with pytest.raises(ValidationError):
        validate_password(password)


def test_password_similar_to_user_attributes_is_rejected():
    """A password close to the admin email is refused."""
    user = UserFactory.build(admin_email="jeanne.dupont@example.com")

    with pytest.raises(ValidationError):
        validate_password("jeanne.dupont@example", user=user)


def test_strong_password_is_accepted():
    """A long, uncommon password passes every rule."""
    validate_password("correct-horse-battery-staple")
