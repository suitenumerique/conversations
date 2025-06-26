"""Serializers for chat application."""

from rest_framework import serializers

from chat import models


class ChatConversationSerializer(serializers.ModelSerializer):
    """Serializer for chat conversations."""

    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversation
        fields = ["id", "title", "created_at", "updated_at", "messages", "owner"]
        read_only_fields = ["id", "created_at", "updated_at", "messages"]
