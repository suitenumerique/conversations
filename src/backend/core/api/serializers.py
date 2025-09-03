"""Client serializers for the conversations core app."""

from rest_framework import serializers

from core import models


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    class Meta:
        model = models.User
        fields = [
            "id",
            "allow_conversation_analytics",
            "email",
            "full_name",
            "short_name",
            "language",
        ]
        read_only_fields = ["id", "email", "full_name", "short_name"]


class UserLightSerializer(UserSerializer):
    """Serialize users with limited fields."""

    id = serializers.SerializerMethodField(read_only=True)
    email = serializers.SerializerMethodField(read_only=True)

    def get_id(self, _user):
        """Return always None. Here to have the same fields than in UserSerializer."""
        return None

    def get_email(self, _user):
        """Return always None. Here to have the same fields than in UserSerializer."""
        return None

    class Meta:
        model = models.User
        fields = ["id", "email", "full_name", "short_name"]
        read_only_fields = ["id", "email", "full_name", "short_name"]
