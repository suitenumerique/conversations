"""Models for chat conversations."""

from django.contrib.auth import get_user_model
from django.db import models

from core.models import BaseModel

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
    - `openai_messages`: A JSON field of OpenAI messages, only for debug purpose, not used.
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
    openai_messages = models.JSONField(
        default=list,
        blank=True,
        help_text="OpenAI messages for the chat conversation, not used",
    )
    messages = models.JSONField(
        default=list,
        blank=True,
        help_text="Stored messages for the chat conversation, sent to frontend",
    )

    agent_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text="Agent usage for the chat conversation, provided by OpenAI API",
    )
