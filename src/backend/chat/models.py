"""Models for chat conversations."""

from typing import Sequence

from django.contrib.auth import get_user_model
from django.db import models

from django_pydantic_field import SchemaField

from core.models import BaseModel

from chat.ai_sdk_types import UIMessage

User = get_user_model()


class ChatConversation(BaseModel):
    """
    Model representing a chat conversation.

    This model stores the details of a chat conversation:
    - `owner`: The user who owns the conversation.
    - `title`: An optional title for the conversation, provided by frontend,
      the 100 first characters of the first user input message.
    - `ui_messages`: A JSON field of UI messages sent by the frontend, all content is
      overridden at each new request from the frontend.
    - `pydantic_messages`: A JSON field of PydanticAI messages, used to store conversation history.
    - `messages`: A JSON field of stored messages for the conversation, sent to frontend
       when loading the conversation.
    - `agent_usage`: A JSON field of agent usage statistics for the conversation,
    """

    owner = models.ForeignKey(
        User,
        related_name="conversations",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    title = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Title of the chat conversation",
    )

    ui_messages = models.JSONField(
        default=list,
        blank=True,
        help_text="UI messages for the chat conversation, sent by frontend, not used",
    )
    pydantic_messages = models.JSONField(
        default=list,
        blank=True,
        help_text="Pydantic messages for the chat conversation, used for history",
    )
    messages: Sequence[UIMessage] = SchemaField(
        schema=list[UIMessage],
        default=list,
        blank=True,
        help_text="Stored messages for the chat conversation, sent to frontend",
    )

    agent_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text="Agent usage for the chat conversation, provided by OpenAI API",
    )

    collection_id = models.CharField(
        blank=True,
        null=True,
        help_text="Collection ID for the conversation, used for RAG document search",
    )


class ChatConversationContextKind(models.TextChoices):
    """Enumeration of chat conversation context kinds."""

    IMAGE = "image"  # Context related to an image in base64 format
    DOCUMENT = "document"


class ChatConversationContext(BaseModel):
    """
    Model representing a chat conversation context.

    This model stores the details of a chat conversation context:
    - `conversation`: The conversation this context belongs to.
    - `kind`: The kind of context (e.g., 'image', 'document').
    - `name`: The key of the context.
    - `content`: The value of the context.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        related_name="contexts",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    kind = models.CharField(
        max_length=50,
        blank=False,
        null=False,
        help_text="Kind of the chat conversation context (e.g., 'image', 'document')",
        choices=ChatConversationContextKind,
    )
    name = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        help_text="Key of the chat conversation context",
    )
    content = models.TextField(
        blank=True,
        null=True,
        help_text="Value of the chat conversation context",
    )

    class Meta:
        unique_together = ("conversation", "name")
