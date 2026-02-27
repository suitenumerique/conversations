"""Models for chat conversations."""

from typing import Sequence

from django.contrib.auth import get_user_model
from django.db import models

from django_pydantic_field import SchemaField

from core.file_upload.enums import AttachmentStatus
from core.models import BaseModel

from chat.ai_sdk_types import UIMessage

User = get_user_model()


class ChatProjectIcon(models.TextChoices):
    """Project icon text choices."""

    FOLDER = "folder", "Folder icon"
    FILE = "file", "File icon"
    PERSO = "perso", "Perso icon"
    GEAR = "gear", "Gear icon"
    MEGAPHONE = "megaphone", "Megaphone icon"
    STAR = "star", "Star icon"
    BOOKMARK = "bookmark", "Bookmark icon"
    CHART = "chart", "Chart icon"
    EURO = "euro", "Euro icon"
    KEY = "key", "Key icon"
    JUSTICE = "justice", "Justice icon"
    BOOK = "book", "Book icon"
    PUZZLE = "puzzle", "Puzzle icon"
    PALETTE = "palette", "Palette icon"
    TERMINAL = "terminal", "Terminal icon"
    CAR = "car", "Car icon"
    MUSIC = "music", "Music icon"
    CHECKMARK = "checkmark", "Checkmark icon"
    LA_SUITE = "la_suite", "La Suite icon"


class ChatProjectColor(models.TextChoices):
    """Project icon color choices. We keep it generic to ease frontend compatibility."""

    COLOR_1 = "color_1", "Color 1"
    COLOR_2 = "color_2", "Color 2"
    COLOR_3 = "color_3", "Color 3"
    COLOR_4 = "color_4", "Color 4"
    COLOR_5 = "color_5", "Color 5"
    COLOR_6 = "color_6", "Color 6"
    COLOR_7 = "color_7", "Color 7"
    COLOR_8 = "color_8", "Color 8"
    COLOR_9 = "color_9", "Color 9"


class ChatProject(BaseModel):
    """Model representing a project that groups conversations together."""

    owner = models.ForeignKey(
        User,
        related_name="projects",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    title = models.CharField(
        max_length=100,
        help_text="Title of the chat project",
    )
    icon = models.CharField(max_length=20, choices=ChatProjectIcon, help_text="Project icon")
    color = models.CharField(
        max_length=20, choices=ChatProjectColor, help_text="Project icon color"
    )

    llm_instructions = models.TextField(
        blank=True,
        help_text="Custom user instructions to be sent to the llm",
    )

    def __str__(self):
        return self.title


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
    title_set_by_user_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the user manually set the title. If set, prevent automatic "
        "title generation.",
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

    project = models.ForeignKey(
        ChatProject,
        related_name="conversations",
        on_delete=models.SET_NULL,  # explicitly avoid Cascade here
        null=True,
        blank=True,
    )

    class Meta:  # pylint: disable=missing-class-docstring
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "project"]),
        ]

    def __str__(self):
        return self.title or str(self.pk)


class ChatConversationAttachment(BaseModel):
    """
    Model representing an attachment associated with a chat conversation.

    This model stores the details of an attachment:
    - `conversation`: The conversation this attachment belongs to.
    - `uploaded_by`: The user who uploaded the attachment.
    - `key`: The file path of the attachment in the object storage.
    - `file_name`: The original name of the attachment file.
    - `content_type`: The MIME type of the attachment file.

    """

    conversation = models.ForeignKey(
        ChatConversation,
        related_name="attachments",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    uploaded_by = models.ForeignKey(
        User,
        related_name="uploaded_attachments",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        help_text="User who uploaded the attachment",
    )
    upload_state = models.CharField(
        max_length=40,
        choices=AttachmentStatus.choices,
        default=AttachmentStatus.PENDING,
    )
    key = models.CharField(
        blank=False,
        null=False,
        help_text="File path of the attachment in the object storage",
    )
    file_name = models.CharField(
        blank=False,
        null=False,
        help_text="Original name of the attachment file",
    )
    content_type = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        help_text="MIME type of the attachment file",
    )
    size = models.PositiveBigIntegerField(null=True, blank=True)

    conversion_from = models.CharField(
        blank=True,
        null=True,
        help_text="Original file key if the Markdown from another file",
    )
