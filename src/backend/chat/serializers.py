"""Serializers for chat application."""

from django_pydantic_field.rest_framework import SchemaField  # pylint: disable=no-name-in-module
from rest_framework import serializers

from chat import models
from chat.ai_sdk_types import UIMessage


class ChatConversationSerializer(serializers.ModelSerializer):
    """Serializer for chat conversations."""

    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    messages = SchemaField(schema=list[UIMessage], read_only=True)

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversation
        fields = ["id", "title", "created_at", "updated_at", "messages", "owner"]
        read_only_fields = ["id", "created_at", "updated_at", "messages"]


class ChatConversationInputSerializer(serializers.Serializer):
    """
    Used to serialize input from Vercel AI SDK when using conversation endpoint.

    See ChatViewSet().post_conversation(...) method for more details.
    """

    messages = SchemaField(schema=list[UIMessage])

    def update(self, instance, validated_data):
        """Update method is not applicable in this context."""
        raise NotImplementedError("`update()` should not be used in this context.")

    def create(self, validated_data):
        """Create method is not applicable in this context."""
        raise NotImplementedError("`create()` should not be used in this context.")


class ChatConversationRequestSerializer(serializers.Serializer):
    """
    Used to serialize query parameters.

    See ChatViewSet().post_conversation(...) method for more details.
    """

    protocol = serializers.CharField(
        required=False,
        default="data",
        help_text="Protocol version to use for the conversation (text or data).",
        allow_blank=True,
        trim_whitespace=True,
    )

    force_web_search = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Force web search.",
    )

    def update(self, instance, validated_data):
        """Update method is not applicable in this context."""
        raise NotImplementedError("`update()` should not be used in this context.")

    def create(self, validated_data):
        """Create method is not applicable in this context."""
        raise NotImplementedError("`create()` should not be used in this context.")

    def validate_protocol(self, value):
        """Validate the protocol field."""
        if value not in ["text", "data"]:
            raise serializers.ValidationError("Protocol must be either 'text' or 'data'.")
        return value
