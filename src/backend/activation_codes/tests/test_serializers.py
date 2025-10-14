"""Tests for activation_codes serializers."""

import pytest

from activation_codes.factories import ActivationCodeFactory, UserActivationFactory
from activation_codes.serializers import (
    ActivationCodeValidationSerializer,
    ActivationStatusSerializer,
    UserActivationSerializer,
)


@pytest.mark.django_db
def test_activation_code_validation_serializer_valid_code():
    """Test validating a valid activation code."""
    # Create a valid activation code
    _activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    serializer = ActivationCodeValidationSerializer(data={"code": "TEST1234ABCD5678"})
    assert serializer.is_valid()
    assert serializer.validated_data["code"] == "TEST1234ABCD5678"


@pytest.mark.django_db
def test_activation_code_validation_serializer_normalize_lowercase():
    """Test that code is normalized to uppercase."""
    # Create a valid activation code
    _activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    serializer = ActivationCodeValidationSerializer(data={"code": "test1234abcd5678"})
    assert serializer.is_valid()
    assert serializer.validated_data["code"] == "TEST1234ABCD5678"


@pytest.mark.django_db
def test_activation_code_validation_serializer_normalize_with_spaces():
    """Test that spaces are removed from code."""
    # Create a valid activation code
    _activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    serializer = ActivationCodeValidationSerializer(data={"code": "TEST 1234 ABCD 5678"})
    assert serializer.is_valid()
    assert serializer.validated_data["code"] == "TEST1234ABCD5678"


@pytest.mark.django_db
def test_activation_code_validation_serializer_normalize_with_dashes():
    """Test that dashes are removed from code."""
    # Create a valid activation code
    _activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    serializer = ActivationCodeValidationSerializer(data={"code": "TEST-1234-ABCD-5678"})
    assert serializer.is_valid()
    assert serializer.validated_data["code"] == "TEST1234ABCD5678"


@pytest.mark.django_db
def test_activation_code_validation_serializer_normalize_mixed():
    """Test that code with spaces, dashes and lowercase is normalized."""
    # Create a valid activation code
    _activation_code = ActivationCodeFactory(code="TEST1234ABCD5678")

    serializer = ActivationCodeValidationSerializer(data={"code": " test-1234 abcd-5678 "})
    assert serializer.is_valid()
    assert serializer.validated_data["code"] == "TEST1234ABCD5678"


@pytest.mark.django_db
def test_activation_code_validation_serializer_missing_code():
    """Test that code field is required."""
    serializer = ActivationCodeValidationSerializer(data={})
    assert not serializer.is_valid()
    assert "code" in serializer.errors


@pytest.mark.django_db
def test_user_activation_serializer():
    """Test serializing a user activation."""
    activation = UserActivationFactory(activation_code__code="TEST1234ABCD5678")

    serializer = UserActivationSerializer(activation)
    data = serializer.data

    assert "id" in data
    assert data["code"] == "TEST1234ABCD5678"
    assert "activated_at" in data
    assert data["activated_at"] is not None


@pytest.mark.django_db
def test_user_activation_serializer_read_only_fields():
    """Test that all fields are read-only."""
    activation = UserActivationFactory()

    serializer = UserActivationSerializer(activation)

    # All fields should be in read_only_fields
    meta = serializer.Meta
    assert set(meta.read_only_fields) == set(meta.fields)


@pytest.mark.django_db
def test_activation_status_serializer_activated():
    """Test serializing activation status for activated user."""
    activation = UserActivationFactory(activation_code__code="TEST1234ABCD5678")

    data = {"is_activated": True, "activation": activation, "requires_activation": True}

    serializer = ActivationStatusSerializer(data)
    serialized_data = serializer.data

    assert serialized_data["is_activated"] is True
    assert serialized_data["activation"] is not None
    assert serialized_data["activation"]["code"] == "TEST1234ABCD5678"
    assert serialized_data["requires_activation"] is True


@pytest.mark.django_db
def test_activation_status_serializer_not_activated():
    """Test serializing activation status for non-activated user."""
    data = {"is_activated": False, "activation": None, "requires_activation": True}

    serializer = ActivationStatusSerializer(data)
    serialized_data = serializer.data

    assert serialized_data["is_activated"] is False
    assert serialized_data["activation"] is None
    assert serialized_data["requires_activation"] is True


@pytest.mark.django_db
def test_activation_status_serializer_activation_not_required():
    """Test serializing activation status when activation is not required."""
    data = {"is_activated": False, "activation": None, "requires_activation": False}

    serializer = ActivationStatusSerializer(data)
    serialized_data = serializer.data

    assert serialized_data["is_activated"] is False
    assert serialized_data["activation"] is None
    assert serialized_data["requires_activation"] is False


@pytest.mark.django_db
def test_activation_status_serializer_all_fields_read_only():
    """Test that all fields in ActivationStatusSerializer are read-only."""
    serializer = ActivationStatusSerializer()

    for field_name, field in serializer.fields.items():
        assert field.read_only is True, f"Field {field_name} should be read-only"
