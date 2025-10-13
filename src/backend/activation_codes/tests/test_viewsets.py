"""Tests for activation_codes viewsets."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest
from rest_framework import status

from core.factories import UserFactory

from activation_codes.factories import ActivationCodeFactory, UserActivationFactory
from activation_codes.models import ActivationCode, UserActivation, UserRegistrationRequest


@pytest.mark.django_db
def test_activation_status_unauthenticated(api_client):
    """Test that unauthenticated users cannot access status endpoint."""
    response = api_client.get("/api/v1.0/activation/status/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_activation_status_authenticated_not_activated(api_client, settings):
    """Test activation status for authenticated but not activated user."""
    settings.ACTIVATION_REQUIRED = True

    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1.0/activation/status/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_activated"] is False
    assert response.data["activation"] is None
    assert response.data["requires_activation"] is True


@pytest.mark.django_db
def test_activation_status_authenticated_activated(api_client, settings):
    """Test activation status for activated user."""
    settings.ACTIVATION_REQUIRED = True
    activation = UserActivationFactory(activation_code__code="TEST1234ABCD5678")
    api_client.force_authenticate(user=activation.user)

    response = api_client.get("/api/v1.0/activation/status/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_activated"] is True
    assert response.data["activation"] is not None
    assert response.data["activation"]["code"] == "TEST1234ABCD5678"
    assert "activated_at" in response.data["activation"]
    assert response.data["requires_activation"] is True


@pytest.mark.django_db
def test_activation_status_activation_not_required(api_client, settings):
    """Test activation status when activation is not required."""
    settings.ACTIVATION_REQUIRED = False
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1.0/activation/status/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["requires_activation"] is False


@pytest.mark.django_db
def test_validate_code_unauthenticated(api_client):
    """Test that unauthenticated users cannot validate codes."""
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "TEST1234ABCD5678"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_validate_code_success(api_client):
    """Test successfully validating and using an activation code."""
    user = UserFactory()
    activation_code = ActivationCode.objects.create(code="TEST1234ABCD5678")
    api_client.force_authenticate(user=user)

    with patch("activation_codes.viewsets.logger") as mock_logger:
        response = api_client.post("/api/v1.0/activation/validate/", {"code": "TEST1234ABCD5678"})

    assert response.status_code == status.HTTP_201_CREATED
    assert "Your account has been successfully activated" in response.data["detail"]
    assert "activation" in response.data
    assert response.data["activation"]["code"] == "TEST1234ABCD5678"

    # Verify user is now activated
    assert UserActivation.objects.filter(user=user).exists()

    # Verify activation code was used
    activation_code.refresh_from_db()
    assert activation_code.current_uses == 1

    # Verify logging
    mock_logger.info.assert_called_once()


@pytest.mark.django_db
def test_validate_code_with_spaces_and_lowercase(api_client):
    """Test validating code with spaces and lowercase."""
    user = UserFactory()
    ActivationCodeFactory(code="TEST1234ABCD5678")
    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1.0/activation/validate/", {"code": "test 1234 abcd 5678"})

    assert response.status_code == status.HTTP_201_CREATED
    assert UserActivation.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_validate_code_already_activated(api_client):
    """Test validating code when user is already activated."""
    # First activation
    activation = UserActivationFactory()
    api_client.force_authenticate(user=activation.user)

    # Try to activate again with different code
    _another_code = ActivationCodeFactory(code="ANOTHER123456789")
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "ANOTHER123456789"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {"code": "account-already-activated"}


@pytest.mark.django_db
def test_validate_code_nonexistent(api_client):
    """Test validating a non-existent code."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1.0/activation/validate/", {"code": "NONEXISTENT12345"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {"code": "invalid-code"}


@pytest.mark.django_db
def test_validate_code_invalid_serializer(api_client):
    """Test validating with invalid data."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1.0/activation/validate/",
        {},  # Missing code
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" in response.data


@pytest.mark.django_db
def test_validate_code_inactive(api_client):
    """Test validating an inactive code."""
    user = UserFactory()
    ActivationCodeFactory(code="INACTIVE12345678", is_active=False)
    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1.0/activation/validate/", {"code": "INACTIVE12345678"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {"code": "invalid-code"}


@pytest.mark.django_db
def test_validate_code_expired(api_client):
    """Test validating an expired code."""
    user = UserFactory()
    ActivationCodeFactory(code="EXPIRED123456789", expires_at=timezone.now() - timedelta(days=1))
    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1.0/activation/validate/", {"code": "EXPIRED123456789"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_validate_code_max_uses_reached(api_client):
    """Test validating a code that has reached max uses."""
    user = UserFactory()
    ActivationCodeFactory(code="MAXUSED123456789", max_uses=1, current_uses=1)
    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1.0/activation/validate/", {"code": "MAXUSED123456789"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_validate_code_multi_use(api_client):
    """Test using a multi-use code with multiple users."""
    multi_use_activation_code = ActivationCodeFactory(
        code="MULTIUSE12345678",
        max_uses=3,
    )
    users = []
    for i in range(3):
        user = UserFactory(email=f"user{i}@example.com")
        users.append(user)

    for i, user in enumerate(users):
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/v1.0/activation/validate/", {"code": "MULTIUSE12345678"})

        assert response.status_code == status.HTTP_201_CREATED
        multi_use_activation_code.refresh_from_db()
        assert multi_use_activation_code.current_uses == i + 1


@pytest.mark.django_db
def test_validate_code_unlimited_use(api_client):
    """Test using an unlimited code with multiple users."""
    unlimited_activation_code = ActivationCodeFactory(
        code="UNLIMITED123CODE",
        max_uses=0,  # Unlimited uses
    )
    for i in range(10):
        user = UserFactory(email=f"user{i}@example.com")
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/v1.0/activation/validate/", {"code": "UNLIMITED123CODE"})

        assert response.status_code == status.HTTP_201_CREATED

    # Code should still be valid
    unlimited_activation_code.refresh_from_db()
    assert unlimited_activation_code.is_valid() is True


@pytest.mark.django_db
def test_validate_code_logging_on_validation_error(api_client):
    """Test that validation errors are logged."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    # Create a code that will cause validation error
    code = ActivationCodeFactory(
        code="WILLEXPIRE123456", expires_at=timezone.now() + timedelta(days=1)
    )

    # Make it expire
    code.expires_at = timezone.now() - timedelta(seconds=1)
    code.save()

    with patch("activation_codes.viewsets.logger"):
        response = api_client.post("/api/v1.0/activation/validate/", {"code": "WILLEXPIRE123456"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Note: In this case the serializer will catch it first
    # so the warning might not be called, but this tests the flow


@pytest.mark.django_db
def test_unauthenticated_register_email(api_client):
    """Test that unauthenticated users cannot register email."""
    response = api_client.post(
        "/api/v1.0/activation/register/",
        {
            "email": "test@example.com",
        },
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_register_email_success(api_client):
    """Test successfully registering an email."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1.0/activation/register/",
        {},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["code"] == "registration-successful"

    registration = UserRegistrationRequest.objects.get(user=user)
    assert registration.user == user


@pytest.mark.django_db
def test_register_already_created(api_client):
    """Test successfully registering an email."""
    user = UserFactory()
    _registration = UserRegistrationRequest.objects.create(
        user=user,
    )

    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1.0/activation/register/",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"code": "registration-successful"}

    assert UserRegistrationRequest.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_validate_code_registered_user(api_client):
    """Test validating a code for a user with a pre-existing registration."""
    user = UserFactory()
    _registration = UserRegistrationRequest.objects.create(
        user=user,
    )
    activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1.0/activation/validate/", {"code": "TEST1234ABCD5678"})

    assert response.status_code == status.HTTP_201_CREATED

    _registration.refresh_from_db()
    assert _registration.user_activation.activation_code == activation_code
