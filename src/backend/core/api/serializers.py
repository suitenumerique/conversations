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
            "allow_smart_web_search",
            "email",
            "full_name",
            "short_name",
            "language",
            "sub",
        ]
        read_only_fields = ["id", "email", "full_name", "short_name", "sub"]
