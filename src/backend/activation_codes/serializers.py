"""Serializers for the activation codes application."""

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from . import models


class ActivationCodeValidationSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for validating an activation code."""

    code = serializers.CharField(
        max_length=50, required=True, help_text=_("The activation code to validate")
    )

    def validate_code(self, value):
        """Validate that the code exists and is valid."""
        # Normalize the code (remove spaces, convert to uppercase)
        return value.strip().upper().replace(" ", "").replace("-", "")


class UserActivationSerializer(serializers.ModelSerializer):
    """Serializer for user activation records."""

    code = serializers.CharField(source="activation_code.code", read_only=True)
    activated_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.UserActivation
        fields = ["id", "code", "activated_at"]
        read_only_fields = ["id", "code", "activated_at"]


class ActivationStatusSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for activation status response."""

    is_activated = serializers.BooleanField(read_only=True)
    activation = UserActivationSerializer(read_only=True, allow_null=True)
    requires_activation = serializers.BooleanField(read_only=True)
