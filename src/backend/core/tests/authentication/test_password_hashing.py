"""Production password hashing and upgrades from existing password hashes."""

from unittest.mock import patch

from django.contrib.auth.hashers import check_password, make_password

import pytest

from core.models import User

from conversations.settings import Base


@pytest.fixture(autouse=True)
def production_password_hashers(settings):
    """Exercise the real hashers instead of the test configuration's fast hasher."""
    settings.PASSWORD_HASHERS = Base.PASSWORD_HASHERS


def test_new_password_uses_argon2id():
    """Hash new passwords with the Argon2id variant and verify them."""
    user = User()
    user.set_password("a-strong-test-password")

    assert user.password.startswith("argon2$argon2id$")
    assert user.check_password("a-strong-test-password")
    assert not user.check_password("incorrect-password")


@pytest.mark.parametrize("hasher", ["pbkdf2_sha256", "pbkdf2_sha1", "scrypt"])
def test_existing_password_is_upgraded_after_successful_verification(hasher):
    """Keep older passwords usable and persist their upgrade only on success."""
    password = "a-strong-test-password"
    encoded = make_password(password, hasher=hasher)
    user = User(password=encoded)

    with patch.object(user, "save") as save:
        assert not user.check_password("incorrect-password")
        assert user.password == encoded
        save.assert_not_called()

        assert user.check_password(password)
        assert user.password.startswith("argon2$argon2id$")
        save.assert_called_once_with(update_fields=["password"])

    assert check_password(password, user.password)
