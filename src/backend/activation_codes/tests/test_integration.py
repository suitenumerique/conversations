"""Integration tests for activation_codes application."""

from datetime import timedelta

from django.utils import timezone

import pytest
from rest_framework import status

from core.factories import UserFactory

from activation_codes.factories import ActivationCodeFactory
from activation_codes.models import ActivationCode, UserActivation


@pytest.mark.django_db
def test_complete_activation_flow(api_client, settings):
    """Test complete user activation flow from registration to usage."""
    settings.ACTIVATION_REQUIRED = True

    # Create a user (simulating registration)
    user = UserFactory(email="newuser@example.com", password="password123")

    # Create an activation code (simulating admin creating codes)
    activation_code = ActivationCode.objects.create(
        code="WELCOME123456789", max_uses=10, description="Welcome batch for new users"
    )

    # User logs in
    api_client.force_authenticate(user=user)

    # Step 1: Check activation status (should not be activated)
    response = api_client.get("/api/v1.0/activation/status/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_activated"] is False
    assert response.data["requires_activation"] is True

    # Step 2: User enters activation code
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "WELCOME123456789"})
    assert response.status_code == status.HTTP_201_CREATED
    assert "successfully activated" in response.data["detail"]

    # Step 3: Check activation status again (should now be activated)
    response = api_client.get("/api/v1.0/activation/status/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_activated"] is True
    assert response.data["activation"]["code"] == "WELCOME123456789"

    # Step 4: Verify in database
    assert UserActivation.objects.filter(user=user).exists()
    activation_code.refresh_from_db()
    assert activation_code.current_uses == 1


@pytest.mark.django_db
def test_activation_not_required_flow(api_client, settings):
    """Test that when activation is not required, users can access without codes."""
    settings.ACTIVATION_REQUIRED = False

    user = UserFactory(email="freeuser@example.com", password="password123")

    api_client.force_authenticate(user=user)

    # Check status
    response = api_client.get("/api/v1.0/activation/status/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["requires_activation"] is False
    assert response.data["is_activated"] is False  # Not activated but not required


@pytest.mark.django_db
def test_multiple_users_same_code(api_client, settings):
    """Test multiple users using the same multi-use code."""
    settings.ACTIVATION_REQUIRED = True

    # Create a multi-use code
    code = ActivationCode.objects.create(
        code="TEAMCODE12345678", max_uses=3, description="Team activation code"
    )

    # Create 3 users
    users = []
    for i in range(3):
        user = UserFactory(email=f"teamuser{i}@example.com", password="password123")
        users.append(user)

    # Each user activates
    for i, user in enumerate(users):
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/v1.0/activation/validate/", {"code": "TEAMCODE12345678"})
        assert response.status_code == status.HTTP_201_CREATED

        code.refresh_from_db()
        assert code.current_uses == i + 1

    # Code should now be exhausted
    code.refresh_from_db()
    assert code.is_valid() is False

    # Try with a 4th user (should fail)
    user4 = UserFactory(email="teamuser4@example.com", password="password123")
    api_client.force_authenticate(user=user4)
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "TEAMCODE12345678"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_code_expiration_scenario(api_client, settings):
    """Test code expiration over time."""
    settings.ACTIVATION_REQUIRED = True

    # Create a code that expires in 1 day
    future_time = timezone.now() + timedelta(days=1)
    _code = ActivationCode.objects.create(code="EXPIRES123456789", expires_at=future_time)

    user = UserFactory(email="timeduser@example.com", password="password123")
    api_client.force_authenticate(user=user)

    # Should work now
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "EXPIRES123456789"})
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_staff_user_bypass(api_client, settings):
    """Test that staff users bypass activation requirement."""
    settings.ACTIVATION_REQUIRED = True

    staff_user = UserFactory(email="staff@example.com", password="password123", is_staff=True)

    api_client.force_authenticate(user=staff_user)

    # Staff should be able to check status even without activation
    response = api_client.get("/api/v1.0/activation/status/")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_user_cannot_activate_twice(api_client, settings):
    """Test that a user cannot activate their account twice."""
    settings.ACTIVATION_REQUIRED = True

    user = UserFactory(email="onceuser@example.com", password="password123")

    _code1 = ActivationCodeFactory(code="FIRST12345678901")
    _code2 = ActivationCodeFactory(code="SECOND1234567890")

    api_client.force_authenticate(user=user)

    # First activation
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "FIRST12345678901"})
    assert response.status_code == status.HTTP_201_CREATED

    # Try second activation
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "SECOND1234567890"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {"code": "account-already-activated"}

    # Verify only one activation exists
    assert UserActivation.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_code_variations_normalized(api_client, settings):
    """Test that different code input formats are normalized correctly."""
    settings.ACTIVATION_REQUIRED = True

    code = ActivationCodeFactory(code="TESTCODE12345678")

    test_cases = [
        "testcode12345678",  # lowercase
        "TESTCODE12345678",  # uppercase
        "test code 1234 5678",  # with spaces
        "TEST-CODE-1234-5678",  # with dashes
        " test-code 1234-5678 ",  # mixed with leading/trailing spaces
    ]

    for i, code_variation in enumerate(test_cases):
        user = UserFactory(email=f"varuser{i}@example.com", password="password123")

        # Update code to allow multiple uses
        code.max_uses = 0
        code.save()

        api_client.force_authenticate(user=user)
        response = api_client.post("/api/v1.0/activation/validate/", {"code": code_variation})
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Failed for variation: {code_variation}"
        )


@pytest.mark.django_db
def test_inactive_code_cannot_be_used(api_client, settings):
    """Test that inactive codes cannot be used even if valid otherwise."""
    settings.ACTIVATION_REQUIRED = True

    _code = ActivationCodeFactory(
        code="INACTIVE123VALID",
        is_active=False,
        max_uses=10,
        expires_at=timezone.now() + timedelta(days=30),
    )

    user = UserFactory(email="blockeduser@example.com", password="password123")

    api_client.force_authenticate(user=user)
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "INACTIVE123VALID"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_concurrent_activations_multi_use_code(api_client, settings):
    """Test that concurrent activations don't exceed max_uses."""
    settings.ACTIVATION_REQUIRED = True

    code = ActivationCodeFactory(code="CONCURRENT123456", max_uses=2)

    # Create 3 users
    users = [
        UserFactory(email=f"concurrent{i}@example.com", password="password123") for i in range(3)
    ]

    # First two should succeed
    for i in range(2):
        api_client.force_authenticate(user=users[i])
        response = api_client.post("/api/v1.0/activation/validate/", {"code": "CONCURRENT123456"})
        assert response.status_code == status.HTTP_201_CREATED

    # Third should fail
    api_client.force_authenticate(user=users[2])
    response = api_client.post("/api/v1.0/activation/validate/", {"code": "CONCURRENT123456"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Verify only 2 activations
    code.refresh_from_db()
    assert code.current_uses == 2
