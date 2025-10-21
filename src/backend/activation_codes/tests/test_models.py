"""Tests for activation_codes models."""

import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.utils import timezone

import pytest
import responses

from core.factories import UserFactory

from activation_codes.exceptions import InvalidCodeError, UserAlreadyActivatedError
from activation_codes.factories import ActivationCodeFactory, UserActivationFactory
from activation_codes.models import (
    ActivationCode,
    UserActivation,
    UserRegistrationRequest,
    generate_activation_code,
)


@pytest.mark.django_db
def test_generate_activation_code():
    """Test that generate_activation_code creates a valid code."""
    code = generate_activation_code()

    assert len(code) == 16
    assert code.isupper()
    assert all(c.isalnum() for c in code)
    # Check that ambiguous characters are not present
    assert "O" not in code
    assert "0" not in code
    assert "I" not in code
    assert "1" not in code


@pytest.mark.django_db
def test_generate_activation_code_uniqueness():
    """Test that generated codes are unique."""
    codes = [generate_activation_code() for _ in range(100)]
    assert len(codes) == len(set(codes))


@pytest.mark.django_db
def test_activation_code_creation():
    """Test creating an activation code."""
    activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    assert activation_code.code == "TEST1234ABCD5678"
    assert activation_code.max_uses == 1
    assert activation_code.current_uses == 0
    assert activation_code.is_active is True
    assert activation_code.expires_at is None


@pytest.mark.django_db
def test_activation_code_auto_generated_code():
    """Test that activation code is auto-generated if not provided."""
    code = ActivationCodeFactory()
    assert len(code.code) == 16
    assert code.code.isupper()


@pytest.mark.django_db
def test_activation_code_str_representation():
    """Test string representation of activation code."""
    activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")
    assert str(activation_code) == "TEST1234ABCD5678 (0/1)"


@pytest.mark.django_db
def test_activation_code_str_representation_unlimited():
    """Test string representation of unlimited activation code."""
    unlimited_activation_code = ActivationCodeFactory(code="UNLIMITED123CODE", max_uses=0)

    assert str(unlimited_activation_code) == "UNLIMITED123CODE (0/∞)"


@pytest.mark.django_db
def test_activation_code_is_valid_active():
    """Test that an active, non-expired code is valid."""
    activation_code = ActivationCodeFactory()
    assert activation_code.is_valid() is True
    assert activation_code.can_be_used() is True


@pytest.mark.django_db
def test_activation_code_is_valid_inactive():
    """Test that an inactive code is not valid."""
    inactive_activation_code = ActivationCodeFactory(is_active=False)
    assert inactive_activation_code.is_valid() is False
    assert inactive_activation_code.can_be_used() is False


@pytest.mark.django_db
def test_activation_code_is_valid_expired():
    """Test that an expired code is not valid."""
    expired_activation_code = ActivationCodeFactory(
        created_at=timezone.now() - timedelta(days=10),
        expires_at=timezone.now() - timedelta(days=1),
    )
    assert expired_activation_code.is_valid() is False
    assert expired_activation_code.can_be_used() is False


@pytest.mark.django_db
def test_activation_code_is_valid_max_uses_reached():
    """Test that a code with max uses reached is not valid."""
    activation_code = ActivationCodeFactory(max_uses=1)
    activation_code.current_uses = 1
    activation_code.save()
    assert activation_code.is_valid() is False


@pytest.mark.django_db
def test_activation_code_is_valid_unlimited_uses():
    """Test that unlimited code is always valid regardless of current uses."""
    unlimited_activation_code = ActivationCodeFactory(max_uses=0)
    unlimited_activation_code.current_uses = 100
    unlimited_activation_code.save()
    assert unlimited_activation_code.is_valid() is True


@pytest.mark.django_db
def test_activation_code_use_success():
    """Test successfully using an activation code."""
    user = UserFactory()
    activation_code = ActivationCodeFactory()
    activation = activation_code.use(user)

    assert isinstance(activation, UserActivation)
    assert activation.user == user
    assert activation.activation_code == activation_code

    # Check that usage counter was incremented
    activation_code.refresh_from_db()
    assert activation_code.current_uses == 1


@pytest.mark.django_db
def test_activation_code_use_invalid_code():
    """Test using an invalid activation code raises error."""
    inactive_activation_code = ActivationCodeFactory(is_active=False)
    user = UserFactory()
    with pytest.raises(InvalidCodeError):
        inactive_activation_code.use(user)


@pytest.mark.django_db
def test_activation_code_use_already_activated():
    """Test using a code when user is already activated raises error."""
    user = UserFactory()
    activation_code = ActivationCodeFactory()

    # First activation
    activation_code.use(user)

    # Try to activate again with a different code
    another_code = ActivationCodeFactory(code="ANOTHER123456789")
    with pytest.raises(UserAlreadyActivatedError):
        another_code.use(user)


@pytest.mark.django_db
def test_activation_code_use_multi_use():
    """Test using a multi-use activation code."""
    multi_use_activation_code = ActivationCodeFactory(max_uses=4)
    users = [UserFactory(email=f"user{i}@example.com") for i in range(3)]

    for i, user in enumerate(users):
        activation = multi_use_activation_code.use(user)
        assert activation.user == user

        multi_use_activation_code.refresh_from_db()
        assert multi_use_activation_code.current_uses == i + 1

    # Code should still be valid
    assert multi_use_activation_code.is_valid() is True


@pytest.mark.django_db
def test_activation_code_use_max_uses_exceeded():
    """Test that code cannot be used when max uses is reached."""
    user = UserFactory()
    activation_code = ActivationCodeFactory(max_uses=1)

    # Use the code
    activation_code.use(user)

    # Try to use it again with another user
    another_user = UserFactory(email="another@example.com")
    with pytest.raises(InvalidCodeError):
        activation_code.use(another_user)


@pytest.mark.django_db
def test_activation_code_expiration():
    """Test that code expires correctly."""
    future_expiry = timezone.now() + timedelta(days=1)
    code = ActivationCodeFactory(code="FUTURE123456789", expires_at=future_expiry)

    assert code.is_valid() is True

    # Manually set to past
    code.expires_at = timezone.now() - timedelta(seconds=1)
    code.save()

    assert code.is_valid() is False


@pytest.mark.django_db
def test_user_activation_str_representation():
    """Test string representation of user activation."""
    user_activation = UserActivationFactory(activation_code__code="TEST1234ABCD5678")

    expected = f"{user_activation.user} - TEST1234ABCD5678"
    assert str(user_activation) == expected


@pytest.mark.django_db
def test_user_activation_one_to_one_relationship():
    """Test that a user can only have one activation."""
    user_activation = UserActivationFactory()

    # Try to create another activation for the same user
    with pytest.raises(ValidationError):  # should be IntegrityError
        UserActivationFactory(user=user_activation.user)


@pytest.mark.django_db
def test_activation_code_protect_on_delete():
    """Test that activation code is protected from deletion when used."""
    user_activation = UserActivationFactory()

    # Try to delete the activation code
    with pytest.raises(ProtectedError):
        user_activation.activation_code.delete()


@pytest.mark.django_db
def test_user_activation_cascade_on_user_delete():
    """Test that activation is deleted when user is deleted."""
    activation = UserActivationFactory()
    activation_id = activation.pk

    activation.user.delete()

    # Activation should be deleted
    assert not UserActivation.objects.filter(id=activation_id).exists()


@pytest.mark.django_db
def test_activation_code_ordering():
    """Test that activation codes are ordered by created_at descending."""
    code1 = ActivationCodeFactory(code="CODE1")
    code2 = ActivationCodeFactory(code="CODE2")
    code3 = ActivationCodeFactory(code="CODE3")

    codes = list(ActivationCode.objects.all())
    assert codes == [code3, code2, code1]


@pytest.mark.django_db
def test_user_activation_ordering():
    """Test that user activations are ordered by created_at descending."""
    code1 = ActivationCodeFactory(code="CODE1", max_uses=3)
    code2 = ActivationCodeFactory(code="CODE2", max_uses=3)

    user1 = UserFactory(email="user1@example.com")
    user2 = UserFactory(email="user2@example.com")

    activation1 = UserActivationFactory(user=user1, activation_code=code1)
    activation2 = UserActivationFactory(user=user2, activation_code=code2)

    activations = list(UserActivation.objects.all())
    assert activations == [activation2, activation1]


@responses.activate
@pytest.mark.django_db(transaction=True)
def test_activation_code_use_success_notify_brevo(settings):
    """Test successfully using an activation code and notify Brevo."""
    settings.BREVO_API_KEY = "test_brevo_api_key"
    settings.BREVO_WAITING_LIST_ID = "test_waiting_list_id"
    settings.BREVO_FOLLOWUP_LIST_ID = "test_followup_list_name"

    brevo_remove_mock = responses.post(
        "https://api.brevo.com/v3/contacts/lists/test_waiting_list_id/contacts/remove",
        json={"message": "Contacts added successfully"},
        status=201,
    )

    brevo_create_contact = responses.post(
        "https://api.brevo.com/v3/contacts",
        status=200,
    )

    brevo_add_mock = responses.post(
        "https://api.brevo.com/v3/contacts/lists/test_followup_list_name/contacts/add",
        json={"message": "Contacts added successfully"},
        status=201,
    )

    user = UserFactory()
    registration = UserRegistrationRequest.objects.create(user=user)
    activation_code = ActivationCodeFactory()
    activation = activation_code.use(user)

    registration.refresh_from_db()
    assert registration.user_activation == activation

    assert len(brevo_remove_mock.calls) == 1
    assert brevo_remove_mock.calls[0].request.headers["api-key"] == "test_brevo_api_key"
    assert json.loads(brevo_remove_mock.calls[0].request.body) == {"emails": [user.email]}

    assert len(brevo_create_contact.calls) == 1
    assert brevo_create_contact.calls[0].request.headers["api-key"] == "test_brevo_api_key"
    assert json.loads(brevo_create_contact.calls[0].request.body) == {
        "email": user.email,
        "updateEnabled": True,
    }

    assert len(brevo_add_mock.calls) == 1
    assert brevo_add_mock.calls[0].request.headers["api-key"] == "test_brevo_api_key"
    assert json.loads(brevo_add_mock.calls[0].request.body) == {"emails": [user.email]}
