"""Tests for the OIDC refresh token key validation in post_setup."""

import pytest
from cryptography.fernet import Fernet

from conversations.settings import Base


def test_refresh_token_key_valid_does_not_raise():
    """A valid Fernet key with refresh token storage enabled must not raise."""

    class TestSettings(Base):
        """Fake test settings with refresh token storage on and a valid key."""

        OIDC_STORE_REFRESH_TOKEN = True
        OIDC_STORE_REFRESH_TOKEN_KEY = Fernet.generate_key().decode()

    # Should not raise
    TestSettings().post_setup()


def test_refresh_token_key_invalid_raises():
    """An invalid Fernet key with refresh token storage enabled must raise ValueError."""

    class TestSettings(Base):
        """Fake test settings with refresh token storage on and a malformed key."""

        OIDC_STORE_REFRESH_TOKEN = True
        OIDC_STORE_REFRESH_TOKEN_KEY = "not-a-valid-fernet-key"

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "OIDC_STORE_REFRESH_TOKEN_KEY" in str(excinfo.value)


def test_refresh_token_key_missing_raises():
    """Refresh token storage enabled without a key (None) must raise ValueError."""

    class TestSettings(Base):
        """Fake test settings with refresh token storage on but no key."""

        OIDC_STORE_REFRESH_TOKEN = True
        OIDC_STORE_REFRESH_TOKEN_KEY = None

    with pytest.raises(ValueError) as excinfo:
        TestSettings().post_setup()

    assert "OIDC_STORE_REFRESH_TOKEN_KEY" in str(excinfo.value)


def test_refresh_token_key_not_validated_when_storage_disabled():
    """An invalid key must not raise when refresh token storage is disabled."""

    class TestSettings(Base):
        """Fake test settings with refresh token storage off and a malformed key."""

        OIDC_STORE_REFRESH_TOKEN = False
        OIDC_STORE_REFRESH_TOKEN_KEY = "not-a-valid-fernet-key"

    # Should not raise — the key is only validated when storage is enabled.
    TestSettings().post_setup()
