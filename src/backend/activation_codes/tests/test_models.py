"""Tests for activation_codes models.

The activation gate is gone; what remains is the historical record, so these tests
cover only the model shape, relations and ordering.
"""

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

import pytest

from core.factories import UserFactory

from activation_codes.factories import ActivationCodeFactory, UserActivationFactory
from activation_codes.models import ActivationCode, UserActivation, generate_activation_code


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
