"""Client serializers for the conversations core app."""

from rest_framework import serializers

from core import models


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    CUSTOM_GUIDELINES_MAX_LENGTH = 2000  # prevent too large prompts, easier to handle here

    custom_guidelines = serializers.CharField(
        max_length=CUSTOM_GUIDELINES_MAX_LENGTH,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )

    class Meta:
        model = models.User
        fields = [
            "id",
            "allow_conversation_analytics",
            "allow_datagouv_connector",
            "allow_smart_web_search",
            "custom_guidelines",
            "email",
            "full_name",
            "short_name",
            "language",
            "sub",
        ]
        read_only_fields = ["id", "email", "full_name", "short_name", "sub"]
