"""Serializers for chat application."""

from django.conf import settings

from django_pydantic_field.rest_framework import SchemaField  # pylint: disable=no-name-in-module
from drf_spectacular.utils import extend_schema_field
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

    def validate_messages(self, messages):
        """Validate that messages is not empty."""
        if not messages:
            raise serializers.ValidationError("This list must not be empty.")
        return messages


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
    model_hrid = serializers.CharField(
        required=False,
        default=None,
        help_text="HRID of the model to use for the conversation.",
        allow_blank=True,
        trim_whitespace=True,
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

    def validate_model_hrid(self, value):
        """Validate the model_hrid field."""
        value = value or None  # Convert empty string to None

        if value and value not in settings.LLM_CONFIGURATIONS:
            raise serializers.ValidationError("Invalid model_hrid.")

        return value


class LLModelSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for LL models."""

    hrid = serializers.CharField(help_text="Human-readable ID of the model.")
    model_name = serializers.CharField(help_text="Name of the model.")
    human_readable_name = serializers.CharField(help_text="Human-readable name of the model.")
    icon = serializers.CharField(
        help_text="Icon representing the model.",
        allow_blank=True,
        required=False,
    )

    # Computed field to indicate if the model is the default model
    is_default = serializers.SerializerMethodField(
        help_text="Indicates if the model is the default model.",
    )

    @staticmethod
    @extend_schema_field(serializers.BooleanField)
    def get_is_default(obj) -> bool:
        """Check if the model is the default model."""
        return obj.hrid == settings.LLM_DEFAULT_MODEL_HRID


class ChatMessageCategoricalScoreSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for chat message scores."""

    message_id = serializers.CharField(help_text="ID of the message to score.")
    name = serializers.HiddenField(default="sentiment")
    value = serializers.ChoiceField(
        choices=["positive", "negative"],
        help_text="Sentiment of the score.",
    )


class LLMConfigurationSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for LLM configuration."""

    models = LLModelSerializer(many=True)
